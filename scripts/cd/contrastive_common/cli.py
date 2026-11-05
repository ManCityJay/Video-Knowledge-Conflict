"""Independent dataset QA → Judge → report; model imports remain lazy."""
from __future__ import annotations

import argparse
import importlib.metadata
import math
import subprocess
import sys
import uuid
from pathlib import Path

from vconflict_pipeline.common import PipelineError, utc_now
from vconflict_pipeline.qa import validate_thinking_token_budget
from vconflict_pipeline.settings import DEFAULT_CASE_DIR, PROJECT_ROOT
from .core import validate_parameters
from .config import from_arguments
from .launcher import (
    add_queue_options, gpu_indices, load_status, new_run, preflight, preview, supervise,
    validate_models, validate_root,
)
from .reporting import write_report
from .storage import (
    GROUPS, make_config, output_lock, prepare_output, read_json, select_sources, validate_output,
)


def parser(method='cd', *, baseline=False):
    result = argparse.ArgumentParser(
        description=('TCD/SEASON baseline GPU queue.' if baseline else
                     f'{"VCD" if method == "cd" else method.upper()} aligned with the main QA/Judge protocol.'),
        allow_abbrev=False)
    add_queue_options(result, required_models=not baseline)
    if baseline:
        result.add_argument('--methods', nargs='+', choices=('tcd', 'season'), default=['tcd', 'season'])
    elif method == 'cd':
        result.add_argument('--methods', nargs='+', choices=('cd', 'tcd', 'season'), default=['cd'],
                            help='VCD accepts cd only; TCD/SEASON have independent entry points')
    else:
        result.set_defaults(methods=[method])
    if method != 'cd' or baseline:
        result.add_argument('--batch-size', default='4' if baseline else 'auto',
                            help='Samples per tensor batch, or auto')
        result.add_argument('--max-batch-size', type=int, default=4 if baseline else 32,
                            help='Initial auto batch ceiling; OOM halves it')
        result.add_argument('--autotune-batch', action='store_true',
                            help='Search batch ceilings online with live speed and memory telemetry')
    result.add_argument('--season-beta', type=float, default=.33, help='SEASON temporal homogenization strength')
    result.add_argument('--noise-step', type=int, default=10)
    result.add_argument('--noise-seed', type=int, default=42)
    result.add_argument('--dataset-dir', type=Path, default=DEFAULT_CASE_DIR)
    result.add_argument('--group', action='append', choices=GROUPS, help='Repeat; default: all four main groups')
    for name in ('case-id', 'video-id', 'question-id'):
        result.add_argument('--' + name, action='append')
    directory = 'baselines' if baseline else 'vcd' if method == 'cd' else method
    result.add_argument('--output', type=Path, default=PROJECT_ROOT / 'results' / directory,
                        help='Output root; method/model subdirectories for baselines, model subdirectories otherwise')
    result.add_argument('--alpha', type=float, default=1.0, help='CD contrast weight (default: 1.0)')
    result.add_argument('--beta', type=float, default=.1, help='CD plausibility threshold (default: 0.1)')
    result.add_argument('--max-new-tokens', type=int, default=8192)
    result.add_argument('--thinking-token-budget', type=int, default=6144)
    result.add_argument('--dtype', choices=('bfloat16', 'float16', 'float32'), default='bfloat16')
    based = result.add_mutually_exclusive_group()
    based.add_argument('--based', action='store_true', dest='based')
    based.add_argument('--no-based', action='store_false', dest='based')
    result.set_defaults(based=baseline)
    result.add_argument('--question-no-based', action='store_true',
                        help='Omit the grounding instruction from the question branch when based is enabled')
    force = result.add_mutually_exclusive_group()
    force.add_argument('--force-qa', action='store_true')
    force.add_argument('--force-judge', action='store_true')
    mode = result.add_mutually_exclusive_group()
    mode.add_argument('--summarize-only', action='store_const', dest='mode', const='summarize',
                      help='Rebuild reports without model or Judge requests')
    mode.add_argument('--qa-only', action='store_const', dest='mode', const='qa',
                      help='Save local QA; leave Judge pending for a later run')
    mode.add_argument('--judge-only', action='store_const', dest='mode', const='judge',
                      help='Judge existing valid QA only; never run inference')
    mode.add_argument('--qa-judge', action='store_const', dest='mode', const='qa-judge',
                      help='Generate local QA and run Judge')
    result.set_defaults(mode='qa' if baseline else 'qa-judge')
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
    if args.method not in ('cd', 'tcd', 'season'):
        raise ValueError('Unknown decoding method')
    if args.method in ('tcd', 'season'):
        if args.batch_size != 'auto' and (not str(args.batch_size).isdigit() or int(args.batch_size) < 1):
            raise ValueError('--batch-size must be auto or a positive integer')
        if args.autotune_batch and args.batch_size != 'auto':
            raise ValueError('--autotune-batch requires TCD/SEASON with --batch-size auto')
        if args.max_batch_size < 1:
            raise ValueError('--max-batch-size must be positive')
    if not math.isfinite(args.season_beta) or not 0 <= args.season_beta <= 1:
        raise ValueError('--season-beta must be finite and in [0, 1]')
    if not 0 <= args.noise_step <= 1000 or args.noise_seed < 0:
        raise ValueError('noise-step must be in [0,1000], noise-seed must be nonnegative')
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
    if args.judge_only and (args.qa_only or args.summarize_only or args.force_qa or args.force_judge):
        raise ValueError('--judge-only cannot be combined with QA, summarize, or force options')
    args.output = args.output.expanduser().resolve()
    args.dataset_dir = args.dataset_dir.expanduser().resolve()
    protected = (args.dataset_dir, PROJECT_ROOT / 'dataset', PROJECT_ROOT / 'videos')
    paths = [args.output] + ([args.max_token_log.expanduser().resolve()] if args.max_token_log else [])
    for path in paths:
        if any(path == root.resolve() or root.resolve() in path.parents for root in protected):
            raise ValueError('VCD outputs and logs must be outside source dataset and videos directories')


def run(args):
    validate(args)
    if args.method == 'cd':
        from cd.vcd.execution import execute
    else:
        from .batch_execution import execute
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
        incomplete = report.get('execution_incomplete', report['incomplete'])
        manifest = read_json(args.output / 'config.json')
        manifest['runs'][-1].update(counts=counts, incomplete=incomplete, judge_pending=report['incomplete'], finished_at=utc_now(),
                                   status='interrupted' if interrupted else 'failed' if error else
                                   'incomplete' if incomplete else 'complete')
        if error:
            manifest['runs'][-1]['error'] = error
        from .storage import atomic_json
        atomic_json(args.output / 'config.json', manifest)
        metrics = report['methods'][args.method]['overall']
        qa, judged = metrics['qa_valid'], metrics['judge_valid']
        total = len(targets)
        print(f"QA: {qa}/{total}; Judge: {judged}/{qa}")
        print(f'This run: {counts}')
        print(f"QA output diagnostics ({args.method}, this run): {report['diagnostics'][args.method]}")
        print(f"Report: {args.output / 'report.json'}")
        return 130 if interrupted else 1 if error or incomplete else 0


def main(argv=None, *, method='cd', baseline=False):
    arguments = parser(method, baseline=baseline)
    args = arguments.parse_args(argv)
    args.qa_only = args.mode == 'qa'
    args.judge_only = args.mode == 'judge'
    args.summarize_only = args.mode == 'summarize'
    try:
        validate_models(args.models)
        if len(set(args.methods)) != len(args.methods):
            raise ValueError('--methods cannot contain duplicates')
        if not baseline and args.methods != [method]:
            raise ValueError('VCD accepts --methods cd only. Use python scripts/cd/tcd/run.py '
                             'or python scripts/cd/season/run.py, or python scripts/cd/run_baselines.py '
                             'for TCD/SEASON; this entry point does not forward methods.')
        args.output = args.output.expanduser().resolve()
        validate_root(args.output)
        configs = []
        for family, method in ((f, m) for f in args.models for m in args.methods):
            config = from_arguments(args, family, method, baseline=baseline)
            if args.max_token_log and len(args.models) * len(args.methods) > 1:
                path = args.max_token_log
                config.max_token_log = path.with_name(f'{path.stem}_{method}_{family}{path.suffix}')
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
            checks = {} if args.summarize_only else preflight(configs, indices, require_judge=not args.qa_only)
            status_path = args.output / 'queue_status.json'
            status = load_status(status_path, 'vcd_queue_status')
            current = new_run([c.job_name for c in configs], checks, gpus=args.gpus)
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
