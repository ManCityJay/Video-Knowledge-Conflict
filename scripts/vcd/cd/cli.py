"""Independent dataset QA → Judge → report; model imports remain lazy."""
from __future__ import annotations

import argparse
import gc
import importlib.metadata
import math
import subprocess
import sys
import uuid
from pathlib import Path

from vconflict_pipeline.common import PipelineError, utc_now
from vconflict_pipeline.qa import validate_thinking_token_budget
from vconflict_pipeline.qa_truncation import MaxTokenLog
from vconflict_pipeline.settings import DEFAULT_CASE_DIR, PROJECT_ROOT
from .core import validate_parameters
from .config import from_arguments
from .launcher import (
    add_queue_options, gpu_indices, load_status, new_run, preflight, preview, supervise,
    validate_models, validate_root,
)
from .reporting import write_report
from .storage import (
    GROUPS, bind_target, current_judgment, current_qa, make_config, matching_records, mutate_case,
    output_lock, prepare_output, read_json, records_for, result_path, select_sources, validate_output,
)


def parser():
    result = argparse.ArgumentParser(
        description='VCD aligned with the main conflict-video QA/Judge protocol.', allow_abbrev=False)
    add_queue_options(result, required_models=True)
    result.add_argument('--dataset-dir', type=Path, default=DEFAULT_CASE_DIR)
    result.add_argument('--group', action='append', choices=GROUPS, help='Repeat; default: all four main groups')
    for name in ('case-id', 'video-id', 'question-id'):
        result.add_argument('--' + name, action='append')
    result.add_argument('--output', type=Path, default=PROJECT_ROOT / 'results/vcd')
    result.add_argument('--alpha', type=float, default=1.0, help='CD contrast weight (default: 1.0)')
    result.add_argument('--beta', type=float, default=.1, help='CD plausibility threshold (default: 0.1)')
    result.add_argument('--max-new-tokens', type=int, default=8192)
    result.add_argument('--thinking-token-budget', type=int, default=6144)
    result.add_argument('--dtype', choices=('bfloat16', 'float16', 'float32'), default='bfloat16')
    result.add_argument('--based', action='store_true')
    result.add_argument('--question-no-based', action='store_true',
                        help='Omit the grounding instruction from the question branch when based is enabled')
    force = result.add_mutually_exclusive_group()
    force.add_argument('--force-qa', action='store_true')
    force.add_argument('--force-judge', action='store_true')
    result.add_argument('--summarize-only', action='store_true', help='Rebuild reports without model or Judge requests')
    result.add_argument('--qa-only', action='store_true', help='Save local QA; leave Judge pending for a later run')
    result.add_argument('--max-token-log', type=Path, help='Append task, phase, budget, answer text and finish reason only on actual truncation')
    result.add_argument('--judge-concurrency', type=int, default=24)
    result.add_argument('--judge-rpm', type=float, default=20)
    result.add_argument('--openrouter-concurrency', type=int, default=24)
    result.add_argument('--openrouter-rpm', type=float, default=20)
    result.add_argument('--timeout', type=int, default=600)
    result.add_argument('--max-retries', type=int, default=4)
    return result


def validate(args):
    validate_parameters(args.alpha, args.beta)
    if args.max_new_tokens <= 0:
        raise ValueError('--max-new-tokens must be positive')
    if args.disable_thinking:
        args.thinking_token_budget = None
    else:
        validate_thinking_token_budget(args.thinking_token_budget, args.max_new_tokens)
    for key in ('judge_concurrency', 'openrouter_concurrency', 'timeout'):
        if getattr(args, key) <= 0:
            raise ValueError(f'--{key.replace("_", "-")} must be positive')
    for key in ('judge_rpm', 'openrouter_rpm'):
        if not math.isfinite(getattr(args, key)) or getattr(args, key) <= 0:
            raise ValueError(f'--{key.replace("_", "-")} must be finite and positive')
    if args.max_retries < 0:
        raise ValueError('--max-retries must be nonnegative')
    if args.summarize_only and (args.force_qa or args.force_judge):
        raise ValueError('--summarize-only cannot be combined with force options')
    if args.qa_only and (args.force_judge or args.summarize_only):
        raise ValueError('--qa-only cannot be combined with --force-judge or --summarize-only')
    args.output = args.output.expanduser().resolve()
    args.dataset_dir = args.dataset_dir.expanduser().resolve()
    protected = (args.dataset_dir, PROJECT_ROOT / 'dataset', PROJECT_ROOT / 'videos')
    paths = [args.output] + ([args.max_token_log.expanduser().resolve()] if args.max_token_log else [])
    for path in paths:
        if any(path == root.resolve() or root.resolve() in path.parents for root in protected):
            raise ValueError('VCD outputs and logs must be outside source dataset and videos directories')


def execute(args, output, targets, config, run_id):
    from .judge import JudgeQueue
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
            elif not args.force_judge:
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
                        from .adapters import load_runtime
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


def run(args):
    validate(args)
    config = make_config(args)
    validate_output(args.output)
    cases, targets = select_sources(args)
    run_id = args.run_id or uuid.uuid4().hex
    with output_lock(args.output):
        prepare_output(args.output, config, cases, run_id)
        counts, error, interrupted = ({}, None, False) if args.summarize_only else execute(
            args, args.output, targets, config, run_id)
        report = write_report(args.output, targets, config, run_id=run_id,
                              counts=counts, run_error=error)
        manifest = read_json(args.output / 'config.json')
        manifest['runs'][-1].update(counts=counts, incomplete=report['incomplete'], finished_at=utc_now(),
                                   status='interrupted' if interrupted else 'failed' if error else
                                   'incomplete' if report['incomplete'] else 'complete')
        if error:
            manifest['runs'][-1]['error'] = error
        from .storage import atomic_json
        atomic_json(args.output / 'config.json', manifest)
        metrics = report['methods']['cd']['overall']
        qa, judged = metrics['qa_valid'], metrics['judge_valid']
        total = len(targets)
        print(f"QA: {qa}/{total}; Judge: {judged}/{qa}")
        print(f'This run: {counts}')
        print(f"QA output diagnostics (cd, this run): {report['diagnostics']['cd']}")
        print(f"Report: {args.output / 'report.json'}")
        return 130 if interrupted else 1 if error or report['incomplete'] else 0


def main(argv=None):
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        validate_models(args.models)
        args.output = args.output.expanduser().resolve()
        validate_root(args.output)
        configs = []
        for family in args.models:
            config = from_arguments(args, family)
            if args.max_token_log and len(args.models) > 1:
                path = args.max_token_log
                config.max_token_log = path.with_name(f'{path.stem}_{family}{path.suffix}')
            validate(config)
            config.model_path = make_config(config)['model_path']
            validate_output(config.output)
            select_sources(config)
            configs.append(config)
        indices = gpu_indices(args.gpus, len(configs))
        phases = [('summarize' if args.summarize_only else 'run', configs)]
        if args.dry_run:
            preview(phases, indices)
            return 0
        with output_lock(args.output):
            validate_root(args.output)
            checks = {} if args.summarize_only else preflight(configs, indices)
            status_path = args.output / 'queue_status.json'
            status = load_status(status_path, 'vcd_queue_status')
            current = new_run(args.models, checks, gpus=args.gpus)
            status['runs'].append(current)
            from .storage import atomic_json
            atomic_json(status_path, status)
            try:
                return supervise(phases, indices, checks, status, current, status_path)
            except Exception as exc:
                current.update(status='failed', finished_at=utc_now(), error=str(exc))
                atomic_json(status_path, status)
                raise
    except KeyboardInterrupt:
        return 130
    except (PipelineError, ValueError, OSError, KeyError, importlib.metadata.PackageNotFoundError,
            subprocess.SubprocessError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
