"""Serial VCD QA persistence and shared Judge admission."""
from __future__ import annotations

import gc
import sys
import uuid

from vconflict_pipeline.common import utc_now
from vconflict_pipeline.qa_truncation import MaxTokenLog
from cd.contrastive_common.storage import (
    bind_target, current_judgment, current_qa, matching_records, mutate_case,
    read_json, records_for, result_path,
)


def execute(args, output, targets, config, run_id):
    from cd.contrastive_common.judge import JudgeQueue
    queue, model, processor, dtype = None, None, None, None
    counts = {'qa': {'executed': 0, 'saved': 0, 'cached': 0, 'failed': 0},
              'judge': {'executed': 0, 'saved': 0, 'cached': 0, 'failed': 0}}
    log = MaxTokenLog(args.max_token_log) if args.max_token_log else None
    run_error, interrupted = None, False
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
            elif not args.force_judge and not args.judge_only:
                counts['qa']['executed'] += 1
                qa_id = uuid.uuid4().hex
                meta = {**binding, 'qa_id': qa_id, 'run_id': run_id,
                        'timestamp': utc_now(), 'judgment': None}
                def save_attempt(partial):
                    def save(case):
                        records = records_for(case, target, 'qa_attempts')
                        records[:] = [r for r in records if r.get('qa_id') != qa_id]
                        records.append({**meta, **partial})
                    mutate_case(path, save)
                def log_truncated(stage):
                    if log:
                        log.append({key: meta[key] for key in (
                            'qa_id', 'run_id', 'timestamp', 'group', 'case_id', 'video_id',
                            'question_id', 'method')} | stage)
                save_attempt({'status': 'running'})
                try:
                    if model is None:
                        from cd.contrastive_common.adapters import load_runtime
                        try:
                            model, processor, dtype = load_runtime(
                                args.model_family, config['model_path'], args.device, args.dtype)
                        except KeyboardInterrupt:
                            save_attempt({'status': 'interrupted', 'error': {
                                'type': 'KeyboardInterrupt', 'message': 'Model loading interrupted'}})
                            raise
                    from .runtime import generate_answer
                    generated = generate_answer(model, processor, target,
                                                args=args, dtype=dtype, on_checkpoint=save_attempt,
                                                on_truncated=log_truncated)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    generated = {'status': 'failed', 'error': {
                        'type': type(exc).__name__, 'message': str(exc)[:1000]}}
                result = {**meta, **generated}
                if result['status'] != 'ok':
                    save_attempt(result)
                    counts['qa']['failed'] += 1
                    print(f"QA: failed {target['label']}/cd: {result['error']['message']}", flush=True)
                    result = None
                    gc.collect()
                    if args.device.startswith('cuda'):
                        import torch
                        torch.cuda.empty_cache()
                else:
                    def save_success(case):
                        attempts = records_for(case, target, 'qa_attempts')
                        attempts[:] = [r for r in attempts if r.get('qa_id') != qa_id]
                        records_for(case, target).append(result)
                    mutate_case(path, save_success)
                    counts['qa']['saved'] += 1
                    print(f"QA: saved {target['label']}/cd", flush=True)
            if result is not None and not args.qa_only:
                if current_judgment(target, result):
                    counts['judge']['cached'] += 1
                else:
                    if queue is None:
                        queue = JudgeQueue(args, [result_path(output, t['group'], t['case_id']) for t in targets], run_id)
                    queue.submit(path, target, result)
    except KeyboardInterrupt:
        interrupted = True
        run_error = {'type': 'KeyboardInterrupt', 'message': 'Interrupted; incomplete phases will run again'}
    except Exception as exc:
        run_error = {'type': type(exc).__name__, 'message': str(exc)[:1000]}
        print(f"Error: {exc}", file=sys.stderr, flush=True)
    finally:
        if queue:
            try:
                queue.close(cancel=interrupted)
            except Exception as exc:
                run_error = {'type': type(exc).__name__, 'message': str(exc)[:1000]}
            counts['judge'].update(queue.counts)
    return counts, run_error, interrupted

