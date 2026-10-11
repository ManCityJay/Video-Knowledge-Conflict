"""Immutable task identities, filter dependencies and per-case task planning."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from .common import PipelineError, require_question_only_compatible, video_case_context
from .evaluation import (
    question_result_selected,
    require_selected_final_answers,
    require_selected_prefix_metadata,
    result_selected,
)
from .evidence import video_sha256
from .filters import (
    control_video,
    effective_prefix,
    qa_allowed,
    scope_id,
    stage_fingerprint,
    stage_state,
)
from .integrity import (
    digest,
    judgment_is_current,
    qa_fingerprint,
    qa_is_current,
    question_content,
)
from .paths import resolve_video_path
from .qa_diagnostics import QADiagnosticStage
from .result_rules import (
    FILTER_RESULT_FIELDS,
    expand_thinking_efforts,
    qa_result_key,
    qa_run_key,
    work_title_prefix_condition,
)
from .runtime import path_key
from .selection import eligible_videos, selected_questions


@dataclass
class Task:
    key: str
    path: Path
    kind: str
    stage: str | None
    video_id: str | None
    question_id: str
    effort: str | None
    fingerprint: str
    binding: str
    prefix: bool | None
    mode: str
    based: bool
    question: dict
    context: dict
    result: dict | None
    video_path: Path | None
    media_key: str | None
    context_text: str | None
    force_slot: tuple | None
    token: str | None = None
    attempts: int = 0
    network_retry_count: int = 0
    final_answer_retry_count: int = 0
    due: float = 0
    prepared: str | None = None

    @property
    def diagnostic_stage(self) -> QADiagnosticStage:
        return ('question_only filter' if self.stage == 'question_only' else
                'control filter' if self.stage == 'control_video' else 'main')


class TaskPlanner:
    def __init__(self, args, runtime, failed, failed_cases, forced, note_cache, error):
        self.args, self.runtime = args, runtime
        self.failed, self.failed_cases, self.forced = failed, failed_cases, forced
        self.note_cache, self.error = note_cache, error
        self.efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
        self.tasks = {}

    def owners(self, case, task):
        video = next((v for v in case['videos'] if v['video_id'] == task.video_id), None)
        context = video_case_context(case, video) if video is not None else case
        question = next(q for q in context['questions'] if q['question_id'] == task.question_id)
        return video, context, question

    def records(self, case, task, result=None):
        video, _, question = self.owners(case, task)
        if task.stage and scope_id(video) != 'case':
            if result:
                for field in FILTER_RESULT_FIELDS:
                    if any(r.get('run_id') == result['run_id'] for r in question.get(field, [])):
                        return question[field]
            return question.setdefault('filter_results', [])
        if task.mode == 'question_only':
            return question.setdefault('question_only_results', [])
        if task.stage:
            return control_video(case, video)['qa_results']
        return video['qa_results']

    def fingerprint(self, case, video, question, stage, mode, prefix, based):
        context = video_case_context(case, video) if video else case
        if stage:
            fp = stage_fingerprint(case, video, question, stage, prefix)
        elif mode == 'question_only':
            fp = stage_fingerprint(case, {'video_id': 'case'}, question, 'question_only', None)
        else:
            fp = qa_fingerprint(case, video, question, mode, prefix, based=based)
        binding = digest([fp, question_content(question), context['conflict_spec']])
        return fp, binding

    def make_task(self, path, case, video, question, effort, kind, stage=None, result=None):
        mode = ('question_only' if stage == 'question_only' else 'video') if stage else self.args.input
        prefix = (effective_prefix(self.args.group, self.args.with_work_title_prefix)
                  if stage == 'control_video' else None if stage else
                  work_title_prefix_condition(self.args.group, mode, self.args.with_work_title_prefix))
        based = False if stage else bool(self.args.based)
        fp, binding = self.fingerprint(case, video, question, stage, mode, prefix, based)
        context = video_case_context(case, video) if video else case
        scope = scope_id(video) if video else 'case'
        slot = (path_key(path), scope, question['question_id'], effort, stage, kind)
        forced = bool(stage and self.args.filter_only and (self.args.force_qa or self.args.force_judge))
        actual = control_video(case, video) if stage == 'control_video' else video
        identity = [path_key(path), scope, mode, (actual or {}).get('video_id') if mode != 'question_only' else None,
                    question['question_id'], self.args.qa_model, effort, prefix, based, kind]
        # Metadata normalization before a filter Judge must not change its task
        # identity. A main Judge and filter Judge of the same answer share it.
        source = ([result['run_id'], result.get('final_answer'), question_content(question),
                   context['conflict_spec'], video_sha256(actual) if mode == 'video' else
                   actual['description']['context_en'] if mode == 'description' else None]
                  if result else binding)
        key = digest([identity, source, self.runtime.id if forced else None])
        if key in self.tasks:
            return self.tasks[key]
        video_path = resolve_video_path(actual['local_path'], must_exist=True) if mode == 'video' else None
        media_key = digest([video_path.suffix, video_sha256(actual)]) if video_path and kind == 'qa' else None
        task = Task(key, path, kind, stage, (video or {}).get('video_id'), question['question_id'],
                    effort, fp, binding, prefix, mode, based, copy.deepcopy(question_content(question)),
                    {'title': context['title'], 'conflict_spec': copy.deepcopy(context['conflict_spec']),
                     'role': 'control' if stage or video is None else video['role']},
                    copy.deepcopy(result), video_path, media_key,
                    actual['description']['context_en'] if mode == 'description' else None,
                    slot if forced else None)
        self.tasks[key] = task
        return task

    def offer(self, pending, task):
        if task.key not in self.failed and task.path not in self.failed_cases:
            pending[task.key] = task

    def plan_case(self, path, case, pending, *, filter_only=False, main_only=False):
        args = self.args
        if not filter_only:
            require_selected_prefix_metadata([(path, case)], args=args, efforts=set(self.efforts))
            require_selected_final_answers([(path, case)], args=args, efforts=set(self.efforts))
        if args.input == 'question_only':
            for q in selected_questions({**case, 'questions': require_question_only_compatible(case)},
                                        set(args.question_id or [])):
                for effort in self.efforts:
                    existing = [r for r in q.get('question_only_results', [])
                                if qa_result_key(r) == qa_run_key('question_only', q['question_id'], args.qa_model, effort)]
                    if not existing:
                        self.offer(pending, self.make_task(path, case, None, q, effort, 'qa'))
                    for r in existing:
                        self.note_cache(path, r, judged=r.get('judgment') is not None)
                        if question_result_selected(q, r, args=args, efforts=set(self.efforts)) and r.get('judgment') is None:
                            self.offer(pending, self.make_task(path, case, None, q, effort, 'judge', result=r))
            return
        for video in eligible_videos(case, input_mode=args.input, selected_video_ids=set(args.video_id or []),
                                     video_scope=args.video_scope, based=args.based):
            context = video_case_context(case, video)
            for q in selected_questions(context, set(args.question_id or [])):
                for effort in self.efforts:
                    passed = True
                    if not main_only:
                        for stage in ('question_only', 'control_video'):
                            prefix = None if stage == 'question_only' else effective_prefix(args.group, args.with_work_title_prefix)
                            state = stage_state(case, video, q, stage, args.qa_model, effort, prefix)
                            slot = (path_key(path), scope_id(video), q['question_id'], effort, stage)
                            force_qa = args.filter_only and args.force_qa and slot + ('qa',) not in self.forced
                            force_judge = args.filter_only and args.force_judge and slot + ('judge',) not in self.forced
                            if state['status'] in ('unjudged', 'passed', 'failed') and not force_qa:
                                self.note_cache(path, state['result'],
                                                judged=state['status'] in ('passed', 'failed') and not force_judge)
                            if state['status'] == 'unavailable':
                                self.error(str(slot), f"Filter unavailable {case['case_id']}/{q['question_id']}: {state['reason']}")
                                passed = False
                                break
                            if force_qa or state['status'] in ('missing', 'stale'):
                                self.offer(pending, self.make_task(path, case, video, q, effort, 'qa', stage))
                                passed = False
                                break
                            if force_judge or state['status'] == 'unjudged':
                                self.offer(pending, self.make_task(path, case, video, q, effort, 'judge', stage, state['result']))
                                passed = False
                                break
                            if state['status'] == 'failed':
                                passed = False
                                break
                    if filter_only:
                        continue
                    # Control is produced by the filter chain. Historical control answers
                    # still receive their selected missing judgments after admission.
                    allowed = qa_allowed(case, video, q, args.qa_model, effort,
                                         effective_prefix(args.group, args.with_work_title_prefix), args.input)
                    if not allowed or (not passed and video['role'] != 'control'):
                        continue
                    prefix = work_title_prefix_condition(args.group, args.input, args.with_work_title_prefix)
                    existing = [r for r in video['qa_results']
                                if qa_is_current(case, video, r) and qa_result_key(r, include_work_title_prefix=prefix is not None)
                                == qa_run_key(args.input, q['question_id'], args.qa_model, effort,
                                              based=args.based, work_title_prefix=prefix)]
                    if not existing and video['role'] != 'control':
                        self.offer(pending, self.make_task(path, case, video, q, effort, 'qa'))
                    for r in existing:
                        self.note_cache(path, r, judged=judgment_is_current(case, video, r))
                        if not r.get('final_answer'):
                            raise PipelineError("Selected QA has no final_answer; run --force-qa")
                        if result_selected(video, r, args=args, efforts=set(self.efforts)) and not judgment_is_current(case, video, r):
                            # Let the filter's Judge own its latest authoritative record.
                            if video['role'] == 'control' and not passed:
                                continue
                            self.offer(pending, self.make_task(path, case, video, q, effort, 'judge', result=r))

    def needed(self, case, task):
        video, _, q = self.owners(case, task)
        fp, binding = self.fingerprint(case, video, q, task.stage, task.mode, task.prefix, task.based)
        if binding != task.binding:
            raise PipelineError("Inputs changed while a task was pending; refusing stale work")
        if task.stage:
            state = stage_state(case, video, q, task.stage, self.args.qa_model, task.effort, task.prefix)
            if task.kind == 'qa':
                return (bool(task.force_slot and self.args.force_qa and task.force_slot not in self.forced)
                        or state['status'] in ('missing', 'stale'))
            if not state['result'] or state['result']['run_id'] != task.result['run_id']:
                return False
            return (bool(task.force_slot and self.args.force_judge and task.force_slot not in self.forced)
                    or state['status'] == 'unjudged')
        records = self.records(case, task)
        if task.kind == 'qa':
            return not any(qa_result_key(r, include_work_title_prefix=task.prefix is not None) ==
                           qa_run_key(task.mode, q['question_id'], self.args.qa_model, task.effort,
                                      based=task.based, work_title_prefix=task.prefix)
                           and (task.mode == 'question_only' or qa_is_current(case, video, r)) for r in records)
        r = next((r for r in records if r.get('run_id') == task.result['run_id']), None)
        return r is not None and (r.get('judgment') is None if task.mode == 'question_only'
                                  else not judgment_is_current(case, video, r))
