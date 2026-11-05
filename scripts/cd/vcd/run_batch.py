#!/usr/bin/env python3
"""Freeze the small82 sample and queue independent, resumable VCD workers."""
from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cd.contrastive_common import GENERATION_PROTOCOLS, SCHEMA_VERSION
from cd.contrastive_common.cli import validate
from cd.contrastive_common.config import FAMILIES, WorkerConfig
from cd.contrastive_common.core import validate_parameters
from cd.contrastive_common.launcher import (
    add_queue_options, gpu_indices, load_status, new_run, preflight, preview, supervise,
    validate_models, validate_root,
)
from cd.contrastive_common.models import MODELS, resolve_model
from cd.contrastive_common.storage import (
    GROUPS, atomic_json, digest_json, output_lock, read_json, select_sources, validate_output,
)
from vconflict_pipeline.common import PipelineError, utc_now
from vconflict_pipeline.settings import AUTHOR_JUDGE_MODEL, DEFAULT_CASE_DIR, PROJECT_ROOT

QUOTAS = dict(zip(GROUPS, (25, 25, 25, 7)))
PARAMETERS = {
    'alpha': 1.0, 'beta': 0.1, 'based': True, 'question_no_based': False,
    'max_new_tokens': 8192, 'thinking_token_budget': 6144, 'thinking_effort': 'default',
    'dtype': 'bfloat16',
    'generation_protocols': {'cd': GENERATION_PROTOCOLS['cd']}, 'vcd_schema_version': SCHEMA_VERSION,
    'judge': {'model': AUTHOR_JUDGE_MODEL, 'concurrency': 24, 'rpm': 20,
              'openrouter_concurrency': 24, 'openrouter_rpm': 20,
              'timeout': 600, 'max_retries': 4},
}


def parser():
    result = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    result.add_argument('--output-root', type=Path,
                        default=PROJECT_ROOT / 'results/vcd/small82_alpha1_based')
    result.add_argument('--beta', type=float, default=PARAMETERS['beta'],
                        help='CD plausibility threshold (default: 0.1); use a separate root when changing it')
    result.add_argument('--no-based', action='store_false', dest='based',
                        help='Disable the video-grounding instruction (default: enabled); use a separate output root')
    result.add_argument('--question-no-based', action='store_true',
                        help='Omit grounding only from the question branch; use a separate output root')
    result.add_argument('--selection-from', type=Path,
                        help='Reuse another selection.json sample without copying its QA/Judge results')
    add_queue_options(result)
    result.add_argument('--smoke-first', action='store_true',
                        help='Require one-question QA + Judge on every selected model before the full batch')
    result.add_argument('--summarize-only', action='store_true',
                        help='Rebuild full reports from the frozen sample without GPU or Judge requests')
    return result


def batch_config(family, parameters):
    judge = parameters['judge']
    return WorkerConfig(
        model_family=family, alpha=parameters['alpha'], beta=parameters['beta'],
        based=parameters['based'],
        question_no_based=parameters.get('question_no_based', False),
        max_new_tokens=parameters['max_new_tokens'],
        thinking_token_budget=parameters['thinking_token_budget'],
        disable_thinking=parameters.get('thinking_effort', 'default') is None,
        dtype=parameters['dtype'], judge_concurrency=judge['concurrency'], judge_rpm=judge['rpm'],
        openrouter_concurrency=judge['openrouter_concurrency'], openrouter_rpm=judge['openrouter_rpm'],
        timeout=judge['timeout'], max_retries=judge['max_retries'])


def task_snapshot(target):
    # Text-only source binding; videos and model weights remain immutable by protocol.
    keys = ('group', 'case_id', 'source_path', 'video_id', 'video_path', 'question_scope',
            'question', 'context', 'work_title', 'work_title_prefix', 'based')
    return {key: target[key] for key in keys}


def task_id(target):
    return (target['group'], target['case_id'], target['video_id'],
            target['question_scope'], target['question']['question_id'])


def snapshots(targets):
    result = sorted((task_snapshot(t) for t in targets), key=task_id)
    if len({task_id(t) for t in result}) != len(result):
        raise ValueError('Duplicate source task identities; refusing an ambiguous selection')
    return result


def verify_tasks(expected, actual, family):
    before, after = {task_id(t): t for t in expected}, {task_id(t): t for t in actual}
    if len(before) != len(expected) or len(after) != len(actual):
        raise ValueError(f'Duplicate frozen task identities ({family})')
    missing, added = sorted(before.keys() - after.keys()), sorted(after.keys() - before.keys())
    changed = sorted(key for key in before.keys() & after.keys() if before[key] != after[key])
    if missing or added or changed:
        raise ValueError(f'Frozen selection mismatch ({family}): missing={missing}, added={added}, '
                         f'changed={changed}. Restore the sources or choose a new output root.')


def read_selection(path, parameters=None):
    manifest = read_json(path)
    # Old manifests used thinking and identical based instructions in both branches.
    stored = {**manifest.get('parameters', {})}
    stored.setdefault('thinking_effort', 'default')
    stored.setdefault('question_no_based', False)
    # Ignore only the retired baseline settings, without rewriting the source manifest.
    current = {**stored}
    current.pop('compare_baseline', None)
    if isinstance(current.get('generation_protocols'), dict):
        current['generation_protocols'] = dict(current['generation_protocols'])
        current['generation_protocols'].pop('baseline', None)
    if (manifest.get('format') != 'vcd_small82_batch' or manifest.get('version') != 1
            or (parameters is not None and current != parameters)
            or manifest.get('dataset_dir') != str(DEFAULT_CASE_DIR.resolve())):
        raise ValueError('Incompatible frozen batch configuration; choose a separate output root')
    if (not isinstance(manifest.get('tasks'), list) or not manifest['tasks']
            or not isinstance(manifest.get('models'), dict) or not manifest['models']
            or not set(manifest['models']).issubset(FAMILIES)):
        raise ValueError('Incomplete selection.json; refusing to reconstruct a frozen sample')
    groups = manifest['groups']
    if list(groups) != list(GROUPS) or any(
            len(groups[g]) != QUOTAS[g] or groups[g] != sorted(set(groups[g])) for g in GROUPS):
        raise ValueError('Invalid frozen group/case selection')
    manifest['parameters'] = stored
    return manifest


def selection(output, *, models, beta=PARAMETERS['beta'], based=True, disable_thinking=False,
              question_no_based=False, selection_from=None):
    parameters = {**PARAMETERS, 'beta': beta, 'based': based, 'question_no_based': question_no_based,
                  'thinking_effort': None if disable_thinking else 'default',
                  'thinking_token_budget': None if disable_thinking else PARAMETERS['thinking_token_budget']}
    path = output / 'selection.json'
    reference = read_selection(selection_from) if selection_from is not None else None
    if reference is not None:
        # Reuse the source sample under this batch's prompt condition, then fully validate it.
        reference['tasks'] = [{**task, 'based': based} for task in reference['tasks']]
    if path.exists():
        manifest = read_selection(path, parameters)
        if reference is not None:
            verify_tasks(reference['tasks'], manifest['tasks'], 'selection-from')
            if reference['groups'] != manifest['groups']:
                raise ValueError('--selection-from differs from the existing frozen sample')
            for family in models:
                if (family in reference['models'] and family in manifest['models']
                        and reference['models'][family] != manifest['models'][family]):
                    raise ValueError(f'--selection-from differs from the frozen {family} model')
    else:
        if output.exists() and any(p.name not in ('.run.lock', 'logs') for p in output.iterdir()):
            raise ValueError('Batch results exist without selection.json; choose a separate output root')
        if reference is not None:
            manifest = {**reference, 'created_at': utc_now(), 'parameters': parameters,
                        'selection_from': str(selection_from.expanduser().resolve())}
        else:
            _, available = select_sources(batch_config(models[0], parameters))
            groups = {}
            for group, count in QUOTAS.items():
                ids = sorted({t['case_id'] for t in available if t['group'] == group})
                if len(ids) < count:
                    raise ValueError(f'{group}: need {count} available cases, found {len(ids)}')
                groups[group] = ids[:count]
            manifest = {'format': 'vcd_small82_batch', 'version': 1, 'created_at': utc_now(),
                        'dataset_dir': str(DEFAULT_CASE_DIR.resolve()), 'groups': groups,
                        'parameters': parameters, 'models': {}}

    groups = manifest['groups']
    case_ids = [case_id for ids in groups.values() for case_id in ids]
    expected_pairs = {(g, c) for g, ids in groups.items() for c in ids}
    expected = manifest.get('tasks')
    for family in models:
        config = replace(batch_config(family, parameters), dataset_dir=Path(manifest['dataset_dir']),
                         group=list(groups), case_id=case_ids)
        cases, targets = select_sources(config)
        actual = snapshots(targets)
        if {(c['group'], c['case_id']) for c in cases} != expected_pairs:
            raise ValueError('Selected case IDs resolve to a different group/case set')
        if expected is None:
            expected = actual
        verify_tasks(expected, actual, family)
        model = {'model': MODELS[family], 'model_path': str(resolve_model(family))}
        if family in manifest['models'] and manifest['models'][family] != model:
            raise ValueError(f'Cached {family} model path changed; restore it or choose a separate output root')
        manifest['models'][family] = model
        validate_output(output / family)
    manifest['tasks'] = expected
    manifest['counts'] = {group: {
        'cases': len(ids),
        'videos': len({(t['case_id'], t['video_id']) for t in expected if t['group'] == group}),
        'qa_per_model': sum(t['group'] == group for t in expected),
    } for group, ids in groups.items()}
    return manifest


def worker_configs(args, manifest, *, smoke=False):
    configs = []
    for family in args.models:
        config = replace(
            batch_config(family, manifest['parameters']), output=args.output_root / family,
            dataset_dir=Path(manifest['dataset_dir']), model_path=manifest['models'][family]['model_path'],
            group=list(manifest['groups']),
            case_id=[case_id for ids in manifest['groups'].values() for case_id in ids],
            summarize_only=args.summarize_only,
            max_token_log=args.output_root / family / 'logs' / 'truncation.jsonl')
        if smoke:
            first = manifest['tasks'][0]
            config = replace(config, group=[first['group']], case_id=[first['case_id']],
                             video_id=[first['video_id']], question_id=[first['question']['question_id']])
        validate(config)
        _, selected = select_sources(config)
        verify_tasks([manifest['tasks'][0]] if smoke else manifest['tasks'], snapshots(selected),
                     family + (' smoke' if smoke else ' launch'))
        configs.append(config)
    return configs


def phases_for(args, manifest):
    if args.summarize_only:
        return [('summarize', worker_configs(args, manifest))]
    phases = [('smoke', worker_configs(args, manifest, smoke=True))] if args.smoke_first else []
    return phases + [('batch', worker_configs(args, manifest))]


def main(argv=None):
    args = parser().parse_args(argv)
    args.output_root = args.output_root.expanduser().resolve()
    try:
        validate_models(args.models)
        validate_parameters(PARAMETERS['alpha'], args.beta)
        validate_root(args.output_root)
        if args.selection_from is not None:
            args.selection_from = args.selection_from.expanduser().resolve(strict=True)
        if args.summarize_only and not (args.output_root / 'selection.json').is_file():
            raise ValueError('--summarize-only requires an existing selection.json')
        protected = (PROJECT_ROOT / 'dataset', PROJECT_ROOT / 'videos')
        if any(args.output_root == p.resolve() or p.resolve() in args.output_root.parents for p in protected):
            raise ValueError('Batch output must be outside source dataset and videos directories')
        options = dict(models=args.models, beta=args.beta, based=args.based,
                       question_no_based=args.question_no_based,
                       disable_thinking=args.disable_thinking,
                       selection_from=args.selection_from)
        manifest = selection(args.output_root, **options)
        print('Frozen sample: ' + str(manifest['counts']), flush=True)
        print(f'Total: {sum(len(ids) for ids in manifest["groups"].values())} cases, '
              f'{sum(c["videos"] for c in manifest["counts"].values())} videos, '
              f'{len(manifest["tasks"])} QA/model; requested models={args.models}', flush=True)
        indices = gpu_indices(args.gpus, len(args.models))
        phases = phases_for(args, manifest)
        if args.dry_run:
            preview(phases, indices)
            return 0
        with output_lock(args.output_root):
            manifest = selection(args.output_root, **options)
            phases = phases_for(args, manifest)
            checks = {} if args.summarize_only else preflight(phases[-1][1], indices, require_judge=True)
            # Persist compatible model additions (including Cosmos) without resampling.
            atomic_json(args.output_root / 'selection.json', manifest)
            status_path = args.output_root / 'batch_status.json'
            status = load_status(status_path, 'vcd_small82_status')
            current = new_run(args.models, checks, selection_sha256=digest_json(manifest), gpus=args.gpus)
            status['runs'].append(current)
            atomic_json(status_path, status)
            try:
                code = supervise(phases, indices, checks, status, current, status_path)
            except Exception as exc:
                current.update(status='failed', finished_at=utc_now(), error=str(exc))
                atomic_json(status_path, status)
                raise
            print(f'Batch {current["status"]}: {status_path}', flush=True)
            return code
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, PipelineError, importlib.metadata.PackageNotFoundError,
            subprocess.SubprocessError) as exc:
        print(f'Error: {exc}', file=sys.stderr, flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
