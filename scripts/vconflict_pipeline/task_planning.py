"""Immutable task identities, filter dependencies and per-case task planning."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from .common import PipelineError, video_case_context
from .evaluation import (
    require_selected_final_answers,
    require_selected_prefix_metadata,
    selected_targets,
    target_results,
)
from .evidence import video_sha256
from .filters import (
    scope_id,
    question_filter_fingerprint,
    question_filter_state,
)
from .integrity import (
    digest,
    judgment_is_current,
    qa_fingerprint,
    question_content,
)
from .paths import resolve_video_path
from .qa_diagnostics import QADiagnosticStage
from .result_rules import (
    FILTER_RESULT_FIELDS,
    expand_thinking_efforts,
    qa_input_mode,
    work_title_prefix_condition,
)
from .runtime import path_key


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
    network_retry_count: int = 0
    final_answer_retry_count: int = 0
    due: float = 0
    prepared: str | None = None

    @property
    def diagnostic_stage(self) -> QADiagnosticStage:
        return 'question_only filter' if self.stage == 'question_only' else 'main'


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
        return video, question

    def records(self, case, task, result=None):
        video, question = self.owners(case, task)
        if task.stage:
            if result:
                for field in (*FILTER_RESULT_FIELDS, 'question_only_results'):
                    if any(r.get('run_id') == result['run_id'] for r in question.get(field, [])):
                        return question[field]
            field = 'question_only_results' if scope_id(video) == 'case' else 'filter_results'
            return question.setdefault(field, [])
        return video['qa_results']

    def fingerprint(self, case, video, question, stage, mode, prefix, based):
        context = video_case_context(case, video) if video else case
        fp = (question_filter_fingerprint(case, video, question) if stage else
              qa_fingerprint(case, video, question, mode, prefix, based=based))
        binding = digest([fp, question_content(question), context['conflict_spec']])
        return fp, binding

    def make_task(self, path, case, video, question, effort, kind, *, stage=None, result=None):
        mode = 'question_only' if stage else qa_input_mode(self.args.input)
        prefix = (None if stage else
                  work_title_prefix_condition(self.args.group, mode, self.args.with_work_title_prefix))
        based = False if stage else bool(self.args.based)
        fp, binding = self.fingerprint(case, video, question, stage, mode, prefix, based)
        context = video_case_context(case, video) if video else case
        scope = scope_id(video)
        slot = (path_key(path), scope, question['question_id'], effort, stage, kind)
        forced = bool(stage and self.args.filter_only and (self.args.force_qa or self.args.force_judge))
        identity = [path_key(path), scope, mode, video['video_id'] if mode != 'question_only' else None,
                    question['question_id'], self.args.qa_model, effort, prefix, based, kind]
        # Filter metadata normalization must not change a Judge task's identity.
        source = ([result['run_id'], result.get('final_answer'), question_content(question),
                   context['conflict_spec'], video_sha256(video) if mode == 'video' else
                   video['description']['context_en'] if mode == 'description' else None]
                  if result else binding)
        key = digest([identity, source, self.runtime.id if forced else None])
        if key in self.tasks:
            return self.tasks[key]
        video_path = resolve_video_path(video['local_path'], must_exist=True) if mode == 'video' else None
        media_key = digest([video_path.suffix, video_sha256(video)]) if video_path and kind == 'qa' else None
        task = Task(
            key=key, path=path, kind=kind, stage=stage,
            video_id=video['video_id'] if video else None,
            question_id=question['question_id'], effort=effort,
            fingerprint=fp, binding=binding, prefix=prefix, mode=mode, based=based,
            question=copy.deepcopy(question_content(question)),
            context={'title': context['title'], 'conflict_spec': copy.deepcopy(context['conflict_spec']),
                     'role': 'control' if stage else video['role']},
            result=copy.deepcopy(result), video_path=video_path, media_key=media_key,
            context_text=video['description']['context_en'] if mode == 'description' else None,
            force_slot=slot if forced else None,
        )
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
        for video, question, effort in selected_targets(case, args=args, efforts=self.efforts,
                                                         enforce_gate=False):
            if not main_only or args.input == 'question_only':
                state = question_filter_state(case, video, question, args.qa_model, effort)
                slot = (path_key(path), scope_id(video), question['question_id'], effort, 'question_only')
                force_qa = args.filter_only and args.force_qa and slot + ('qa',) not in self.forced
                force_judge = args.filter_only and args.force_judge and slot + ('judge',) not in self.forced
                if state['status'] in ('unjudged', 'passed', 'failed') and not force_qa:
                    self.note_cache(path, state['result'],
                                    judged=state['status'] in ('passed', 'failed') and not force_judge)
                if state['status'] == 'unavailable':
                    self.error(str(slot), f"Filter unavailable {case['case_id']}/{question['question_id']}: {state['reason']}")
                    continue
                if force_qa or state['status'] in ('missing', 'stale'):
                    self.offer(pending, self.make_task(path, case, video, question, effort, 'qa', stage='question_only'))
                    continue
                if force_judge or state['status'] == 'unjudged':
                    self.offer(pending, self.make_task(path, case, video, question, effort, 'judge',
                                                       stage='question_only', result=state['result']))
                    continue
                if state['status'] == 'failed':
                    continue
            if filter_only or args.input == 'question_only':
                continue
            if main_only and question_filter_state(case, video, question, args.qa_model, effort)['status'] != 'passed':
                continue
            existing = target_results(case, video, question, effort, args=args)
            if not existing:
                self.offer(pending, self.make_task(path, case, video, question, effort, 'qa'))
            for result in existing:
                judged = judgment_is_current(case, video, result)
                self.note_cache(path, result, judged=judged)
                if not judged:
                    self.offer(pending, self.make_task(path, case, video, question, effort, 'judge', result=result))

    def needed(self, case, task):
        video, question = self.owners(case, task)
        _, binding = self.fingerprint(case, video, question, task.stage, task.mode, task.prefix, task.based)
        if binding != task.binding:
            raise PipelineError("Inputs changed while a task was pending; refusing stale work")
        if task.stage:
            state = question_filter_state(case, video, question, self.args.qa_model, task.effort)
            if task.kind == 'qa':
                return (bool(task.force_slot and self.args.force_qa and task.force_slot not in self.forced)
                        or state['status'] in ('missing', 'stale'))
            if not state['result'] or state['result']['run_id'] != task.result['run_id']:
                return False
            return (bool(task.force_slot and self.args.force_judge and task.force_slot not in self.forced)
                    or state['status'] == 'unjudged')
        records = target_results(case, video, question, task.effort, args=self.args)
        if task.kind == 'qa':
            return not records
        result = next((r for r in records if r.get('run_id') == task.result['run_id']), None)
        return result is not None and not judgment_is_current(case, video, result)
