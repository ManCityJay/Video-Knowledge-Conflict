"""Compact case artifacts, text cache keys and atomic merging."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from vconflict_pipeline.common import PipelineError, utc_now, video_case_context
from vconflict_pipeline.integrity import question_content
from vconflict_pipeline.paths import resolve_video_path
from vconflict_pipeline.runtime import FileLock
from vconflict_pipeline.selection import selected_questions
from vconflict_pipeline.settings import (
    AUTHOR_JUDGE_MODEL, FAIRY_TALE_GROUP, VERDICTS,
)
from vconflict_pipeline.storage import load_case
from . import GENERATION_PROTOCOLS, PROTOCOL_VERSION, SCHEMA_VERSION
from .models import MODELS, resolve_model
from .video import build_messages

GROUPS = (FAIRY_TALE_GROUP, 'classic_physics_chemistry_experiments',
          'real_world_commonsense_conflicts', 'mathematics_algorithm_conflicts')


def digest_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_text(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


@contextmanager
def output_lock(output):
    output.mkdir(parents=True, exist_ok=True)
    lock = FileLock(output / '.run.lock')
    try:
        if not lock.acquire(False):
            raise ValueError(f'Another VCD run is using {output}')
        yield
    finally:
        lock.close()


def mutate_case(path, callback):
    # Persistent flock + reread avoids lost updates from parallel Judge completions.
    with FileLock(path.parent / '.locks' / (path.name + '.lock')):
        case = read_json(path)
        if case.get('vcd_schema_version') != SCHEMA_VERSION:
            raise ValueError(f'Unsupported VCD result format: {path}')
        callback(case)
        case['updated_at'] = utc_now()
        atomic_json(path, case)
        return case


def result_path(output, group, case_id):
    return output / 'cases' / group / f'{case_id}.json'


def selected_videos(case, selected_ids):
    # Main selection checks observation hashes. VCD assumes immutable videos.
    candidates = [v for v in case['videos'] if v['role'] == 'conflict']
    missing = selected_ids - {v['video_id'] for v in candidates}
    if missing:
        raise PipelineError(f"Conflict video IDs not found in {case['case_id']}: {', '.join(sorted(missing))}")
    selected = []
    for video in candidates:
        if selected_ids and video['video_id'] not in selected_ids:
            continue
        if video['status'] != 'ready':
            if video['video_id'] in selected_ids:
                raise PipelineError(f"Selected video {case['case_id']}/{video['video_id']} is not ready.")
            continue
        observation = video.get('video_observation')
        if observation is None and video.get('require_video_observation'):
            raise PipelineError(f"Review the generated pixels before annotations: {video['video_id']}")
        if observation is not None:
            summary = observation.get('summary_en')
            if not isinstance(summary, str) or not summary.strip():
                raise PipelineError('A visual observation needs a nonempty summary_en.')
        selected.append(video)
    return selected


def select_sources(args):
    root = args.dataset_dir.resolve(strict=True)
    selected_groups = tuple(dict.fromkeys(args.group or GROUPS))
    cases, targets, found = [], [], set()
    for group in selected_groups:
        directory = root / group
        if not directory.is_dir():
            raise ValueError(f'Dataset group directory does not exist: {directory}')
        for path in sorted(directory.glob('*.json')):
            if args.case_id and path.stem not in args.case_id:
                continue
            case = load_case(path)
            if case.get('canonical_case_path'):
                raise ValueError(f'Historical variant snapshots are not formal cases: {path}')
            found.add(case['case_id'])
            videos = selected_videos(case, set(args.video_id or []))
            selected = []
            for video in videos:
                context = video_case_context(case, video)
                questions = selected_questions(context, set(args.question_id or []))
                video_path = resolve_video_path(video['local_path'], must_exist=True)
                snapshot = {k: copy.deepcopy(video[k]) for k in (
                    'video_id', 'role', 'status', 'local_path', 'question_ids') if k in video}
                if video.get('variant_context') is not None:
                    snapshot['variant_context'] = {
                        'title': context['title'], 'conflict_spec': copy.deepcopy(context['conflict_spec']),
                        'questions': [question_content(q) for q in context['questions']]}
                selected.append(snapshot)
                work_title = context['title'].split(':', 1)[0].strip() if group == FAIRY_TALE_GROUP else None
                for question in questions:
                    scope = video['video_id'] if video.get('variant_context') is not None else 'case'
                    target = {'group': group, 'case_id': case['case_id'], 'source_path': str(path.resolve()),
                              'video_id': video['video_id'], 'video_path': str(video_path),
                              'question_scope': scope,
                              'question': question_content(question), 'context': {
                                  'title': context['title'], 'conflict_spec': context['conflict_spec']},
                              'work_title': work_title, 'work_title_prefix': work_title is not None,
                              'based': args.based,
                              'label': f"{group}/{case['case_id']}/{video['video_id']}/{question['question_id']}"}
                    target['messages'] = build_messages(question['text_en'], family=args.model_family,
                                                       video=video_path, based=args.based, work_title=work_title,
                                                       thinking=not args.disable_thinking)
                    target['question_messages'] = build_messages(
                        question['text_en'], family=args.model_family,
                        based=args.based and not args.question_no_based, work_title=work_title,
                        thinking=not args.disable_thinking)
                    targets.append(target)
            cases.append({'vcd_schema_version': SCHEMA_VERSION, 'group': group,
                          'case_id': case['case_id'], 'source_path': str(path.resolve()),
                          'title': case['title'], 'conflict_spec': case['conflict_spec'],
                          'questions': [question_content(q) for q in case['questions']], 'videos': selected})
    missing = set(args.case_id or []) - found
    if missing:
        raise ValueError(f'Case IDs not found in selected groups: {sorted(missing)}')
    return cases, targets


def make_config(args):
    return {'model_family': args.model_family, 'model': MODELS[args.model_family],
            'model_path': args.model_path or str(resolve_model(args.model_family)),
            'protocol_version': PROTOCOL_VERSION, 'generation_protocols': dict(GENERATION_PROTOCOLS),
            'dtype': args.dtype,
            'max_new_tokens': args.max_new_tokens, 'thinking_token_budget': args.thinking_token_budget,
            'thinking_effort': args.thinking_effort,
            'alpha': args.alpha, 'beta': args.beta, 'based': args.based,
            'question_no_based': args.question_no_based,
            'device': args.device,
            'qa_only': args.qa_only, 'summarize_only': args.summarize_only,
            'force_qa': args.force_qa, 'force_judge': args.force_judge,
            'judge': {'model': AUTHOR_JUDGE_MODEL, 'concurrency': args.judge_concurrency,
                      'rpm': args.judge_rpm, 'openrouter_concurrency': args.openrouter_concurrency,
                      'openrouter_rpm': args.openrouter_rpm, 'timeout': args.timeout,
                      'max_retries': args.max_retries},
            'selection': {key: str(getattr(args, key)) if key == 'dataset_dir' else getattr(args, key)
                          for key in ('dataset_dir', 'group', 'case_id', 'video_id', 'question_id')}}


def bind_target(target, config):
    binding = {key: target[key] for key in (
        'group', 'case_id', 'source_path', 'video_id', 'video_path', 'question_scope',
        'based', 'work_title', 'work_title_prefix')}
    binding.update({key: config[key] for key in (
        'model_family', 'model', 'model_path', 'dtype',
        'max_new_tokens', 'thinking_token_budget')})
    binding.update(question_id=target['question']['question_id'],
                   question=target['question']['text_en'], method='cd',
                   thinking_effort=config.get('thinking_effort', 'default'),
                   protocol_version=config['generation_protocols']['cd'])
    binding.update(alpha=config['alpha'], beta=config['beta'])
    # Preserve historical keys unless the question branch's prompt actually changes.
    if target['based'] and config.get('question_no_based', False) and config['alpha']:
        binding['question_no_based'] = True
    return {**binding, 'qa_key': digest_json(binding)}


def judge_key(target, result):
    from vconflict_pipeline.judging import JUDGE_SYSTEM_PROMPT, judge_payload
    from vconflict_pipeline.schema import JUDGMENT_SCHEMA
    return digest_json({'version': 1, 'payload': judge_payload(
        question=target['question'], facts=target['context']['conflict_spec'],
        role='conflict', final_answer=result['final_answer']),
        'model': AUTHOR_JUDGE_MODEL, 'prompt': JUDGE_SYSTEM_PROMPT, 'schema': JUDGMENT_SCHEMA})


def current_judgment(target, result):
    judgment = result.get('judgment')
    confidence = judgment.get('confidence') if isinstance(judgment, dict) else None
    return (isinstance(judgment, dict) and judgment.get('verdict') in VERDICTS
            and not isinstance(confidence, bool) and isinstance(confidence, (int, float))
            and 0 <= confidence <= 1 and judgment.get('judge_key') == judge_key(target, result))


def records_for(case, target, field='qa_results'):
    video = next(v for v in case['videos'] if v['video_id'] == target['video_id'])
    return video.setdefault(field, [])


def matching_records(case, target, binding, field='qa_results'):
    return [r for r in records_for(case, target, field)
            if r.get('method') == 'cd' and r.get('qa_key') == binding['qa_key']]


def current_qa(case, target, binding):
    from vconflict_pipeline.qa import MissingFinalAnswerError, extract_final_answer
    def valid(record):
        if (record.get('status') != 'ok' or record.get('finish_reason') != 'stop'
                or record.get('invalidated_at')
                or not isinstance(record.get('raw_answer'), str)
                or not isinstance(record.get('final_answer'), str) or not record['final_answer'].strip()):
            return False
        try:
            return extract_final_answer(record.get('raw_answer', '')) == record.get('final_answer')
        except MissingFinalAnswerError:
            return False
    return max((r for r in matching_records(case, target, binding) if valid(r)),
               key=lambda r: (r.get('timestamp', ''), r.get('run_id', '')), default=None)


def validate_output(output):
    """Reject incompatible directories before creating locks or writing artifacts."""
    if not output.exists():
        return
    path = output / 'config.json'
    if not path.exists():
        if any(p.name not in ('.run.lock', 'logs') for p in output.iterdir()):
            raise ValueError('Output has no current VCD manifest; choose a new output directory')
        return
    manifest = read_json(path)
    if manifest.get('format') != 'vcd_cases' or manifest.get('vcd_schema_version') != SCHEMA_VERSION:
        raise ValueError('Old VCD outputs are not migrated; choose a new output directory')
    for case_path in (output / 'cases').rglob('*.json'):
        if read_json(case_path).get('vcd_schema_version') != SCHEMA_VERSION:
            raise ValueError(f'Incompatible case result: {case_path}; choose a new output directory')


def prepare_output(output, config, cases, run_id):
    validate_output(output)
    path = output / 'config.json'
    manifest = read_json(path) if path.exists() else {
        'format': 'vcd_cases', 'vcd_schema_version': SCHEMA_VERSION, 'runs': []}
    for snapshot in cases:
        case_path = result_path(output, snapshot['group'], snapshot['case_id'])
        if case_path.exists():
            existing = read_json(case_path)
            if (existing.get('vcd_schema_version') != SCHEMA_VERSION or
                    (existing.get('group'), existing.get('case_id')) != (snapshot['group'], snapshot['case_id'])):
                raise ValueError(f'Incompatible case result: {case_path}')
    manifest['runs'].append({'run_id': run_id, 'timestamp': utc_now(),
                             'parameters': {k: v for k, v in config.items() if k != 'selection'},
                             'selection': config['selection'], 'status': 'running'})
    atomic_json(path, manifest)
    for snapshot in cases:
        case_path = result_path(output, snapshot['group'], snapshot['case_id'])
        if not case_path.exists():
            atomic_json(case_path, {**snapshot, 'created_at': utc_now()})
        else:
            def merge(existing):
                old = {v['video_id']: v for v in existing['videos']}
                for video in snapshot['videos']:
                    previous = old.setdefault(video['video_id'], {})
                    previous.update(video)
                existing.update({k: v for k, v in snapshot.items() if k != 'videos'})
                existing['videos'] = list(old.values())
            mutate_case(case_path, merge)
