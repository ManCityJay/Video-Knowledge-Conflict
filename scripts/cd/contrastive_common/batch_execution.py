"""Incremental case persistence and shared Judge admission for batched baselines."""
from __future__ import annotations

import gc
import json
import time
import uuid

from vconflict_pipeline.common import utc_now
from vconflict_pipeline.qa_truncation import MaxTokenLog
from .judge import JudgeQueue
from .storage import (
    bind_target, current_judgment, current_qa, matching_records, mutate_case,
    read_json, records_for, result_path,
)


def execute(args, output, targets, config, run_id):
    if args.method not in ('tcd', 'season'):
        raise ValueError('Tensor batch execution supports TCD/SEASON only; VCD uses its serial runtime')
    started = time.perf_counter()
    counts = {'qa': {'executed': 0, 'saved': 0, 'cached': 0, 'failed': 0},
              'judge': {'executed': 0, 'saved': 0, 'cached': 0, 'failed': 0},
              'timing': {'model_load_seconds': 0., 'batch_wall_seconds': 0.,
                         'oom_wall_seconds': 0., 'tensor_batches': 0}}
    log = MaxTokenLog(args.max_token_log or output / 'max_token' / f'{run_id}.jsonl')
    queue, run_error, interrupted, model = None, None, False, None
    pending, metadata = [], []
    completed = set()

    def submit(path, target, result):
        nonlocal queue
        if args.qa_only:
            return
        if current_judgment(target, result):
            counts['judge']['cached'] += 1
        else:
            if queue is None:
                queue = JudgeQueue(args, [result_path(output, t['group'], t['case_id']) for t in targets], run_id)
            queue.submit(path, target, result)

    def save_attempt(index, partial):
        target, meta = pending[index], metadata[index]
        def save(case):
            records = records_for(case, target, 'qa_attempts')
            records[:] = [r for r in records if r.get('qa_id') != meta['qa_id']]
            records.append({**meta, **partial})
        mutate_case(result_path(output, target['group'], target['case_id']), save)

    def truncated(index, stage):
        meta = metadata[index]
        log.append({key: meta[key] for key in (
            'qa_id', 'run_id', 'timestamp', 'group', 'case_id', 'video_id', 'question_id', 'method')} | stage)

    def batch(audit):
        path = output / 'batches' / f'{run_id}.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'run_id': run_id, 'timestamp': utc_now(),
                                     'method': args.method, 'model_family': args.model_family,
                                     **audit}, ensure_ascii=False, allow_nan=False) + '\n')
            stream.flush()
        timing = counts['timing']
        if audit.get('status') == 'oom':
            timing['oom_wall_seconds'] += audit['wall_seconds']
        else:
            timing['batch_wall_seconds'] += audit['wall_seconds']
            timing['tensor_batches'] += 1

    try:
        for target in targets:
            path = result_path(output, target['group'], target['case_id'])
            binding = bind_target(target, config)
            case = read_json(path)
            result = current_qa(case, target, binding)
            if args.force_qa or (args.force_judge and result):
                def invalidate(case):
                    for record in matching_records(case, target, binding):
                        if args.force_qa:
                            record['invalidated_at'] = utc_now()
                        elif record.get('qa_id') == result['qa_id']:
                            record['judgment'] = None
                            record.pop('judge_error', None)
                case = mutate_case(path, invalidate)
                result = current_qa(case, target, binding)
            if result is not None:
                counts['qa']['cached'] += 1
                submit(path, target, result)
            elif not args.force_judge and not args.judge_only:
                pending.append(target)
                metadata.append({**binding, 'qa_id': uuid.uuid4().hex, 'run_id': run_id,
                                 'timestamp': utc_now(), 'judgment': None})
        if pending:
            from .adapters import load_runtime
            from .batch_runtime import generate_answers
            tick = time.perf_counter()
            model, processor, dtype = load_runtime(args.model_family, config['model_path'], args.device, args.dtype)
            counts['timing']['model_load_seconds'] = round(time.perf_counter() - tick, 6)
            for index in range(len(pending)):
                save_attempt(index, {'status': 'running'})
            counts['qa']['executed'] = len(pending)
            for index, generated in generate_answers(
                    model, processor, pending, args=args, dtype=dtype, on_checkpoint=save_attempt,
                    on_truncated=truncated, on_batch=batch):
                target, meta = pending[index], metadata[index]
                result = {**meta, **generated}
                path = result_path(output, target['group'], target['case_id'])
                if result['status'] != 'ok':
                    save_attempt(index, result)
                    counts['qa']['failed'] += 1
                    print(f"QA: failed {target['label']}/{args.method}: {result['error']['message']}", flush=True)
                else:
                    def save(case):
                        attempts = records_for(case, target, 'qa_attempts')
                        attempts[:] = [r for r in attempts if r.get('qa_id') != meta['qa_id']]
                        records_for(case, target).append(result)
                    mutate_case(path, save)
                    counts['qa']['saved'] += 1
                    print(f"QA: saved {target['label']}/{args.method}; seconds={result['seconds']}", flush=True)
                    submit(path, target, result)
                completed.add(index)
    except KeyboardInterrupt:
        interrupted = True
        run_error = {'type': 'KeyboardInterrupt', 'message': 'Interrupted; incomplete tasks will run again'}
    except Exception as exc:
        run_error = {'type': type(exc).__name__, 'message': str(exc)[:1000]}
        print(f'Error: {run_error}', flush=True)
    finally:
        # GPU allocations are released while pending Judge requests drain.
        if model is not None:
            del model
            gc.collect()
            import torch
            torch.cuda.empty_cache()
        counts['timing']['qa_wall_seconds'] = round(time.perf_counter() - started, 6)
        if run_error:
            for index in range(len(pending)):
                if index not in completed:
                    # Preserve generation checkpoints (including phases and timings).
                    target = pending[index]
                    path = result_path(output, target['group'], target['case_id'])
                    def mark(case):
                        rows = records_for(case, target, 'qa_attempts')
                        record = next((r for r in rows if r.get('qa_id') == metadata[index]['qa_id']), None)
                        if record is None:
                            record = dict(metadata[index])
                            rows.append(record)
                        record.update(status='interrupted' if interrupted else 'failed', error=run_error)
                    mutate_case(path, mark)
        if queue:
            try:
                queue.close(cancel=interrupted)
            except Exception as exc:
                run_error = {'type': type(exc).__name__, 'message': str(exc)[:1000]}
            counts['judge'].update(queue.counts)
        counts['timing']['run_wall_seconds'] = round(time.perf_counter() - started, 6)
    return counts, run_error, interrupted
