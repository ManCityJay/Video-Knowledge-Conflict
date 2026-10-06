"""Request-level QA DAG, shared admission, delayed retries and merge commits."""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import time
from collections import Counter, OrderedDict, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .core import (FILTER_RESULT_FIELDS, JUDGMENT_SCHEMA, PipelineError, atomic_write_json,
                   filter_field, grouped_dir, iter_case_paths, load_case,
                   require_question_only_compatible, resolve_video_path, set_filter_field,
                   utc_now, video_case_context)
from .evidence import video_sha256
from .filters import (control_video, effective_prefix, qa_allowed, scope_id,
                      stage_fingerprint, stage_state, question_gate)
from .integrity import (
    digest, judgment_fingerprint, judgment_is_current, qa_fingerprint,
    qa_is_current, question_content,
)
from .qa import (LOCAL_QA_CONFIGS, _dashscope_base_http_api_url, _local_video_uri,
                 _qwen_video_uri, _require_dashscope_sdk, expand_thinking_efforts,
                 get_backend, local_qa_max_tokens, preflight_qa_backend, qa_result_key,
                 qa_run_key, run_qa_batch, work_title_prefix_condition)
from .qa_diagnostics import QADiagnostics
from .runtime import Runtime, case_lock, path_key
from .selection import eligible_videos, selected_questions
from .settings import AUTHOR_JUDGE_MODEL, GEMINI_QA_MODEL, QWEN_QA_MODEL, VERDICTS
from .transport import (OPENROUTER_URL, TransportError, _is_retryable, openrouter_json,
                        require_openrouter_api_key)


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
    due: float = 0
    prepared: str | None = None


class Engine:
    def __init__(self, args, runtime, loaded, diagnostics):
        self.args, self.runtime, self.diagnostics = args, runtime, diagnostics
        self.cases = dict(loaded)
        self.efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
        self.backend = get_backend(args.qa_model)
        self.api_key = os.environ.get(self.backend.api_key_variable, '').strip() if self.backend.api_key_variable else ''
        self.judge_key = os.environ.get('OPENROUTER_API_KEY', '').strip()
        self.served = None
        self.backend_ready = False
        self.tasks = {}
        self.failed = set()
        self.failed_cases = set()
        self.forced = set()
        self.main_only = False
        self.filter_only = False
        self.versions = runtime.versions()
        self.completed = Counter()
        self.attempts = Counter()
        self.cached = set()
        self.cache_records = {'qa': set(), 'judge': set()}
        self.produced_runs = {'qa': set(), 'judge': set()}
        self.waiting_keys = set()
        self.case_plans = {}
        self.dirty = set(self.cases)
        self.main_reservations = set()
        self.last_case = {}
        self.ticks = Counter()
        self.next_pool = 0
        self.preparing = {}
        self.media = OrderedDict()
        self.media_active = Counter()
        self.media_bytes = 0
        self.media_budget = 512 * 1024 * 1024
        self.started = time.monotonic()
        self.interrupted = False
        self.resources = self._resources()
        self.runtime.configure(self.resources)
        print(f"Concurrency: QA={args.qa_concurrency}, Judge={args.judge_concurrency}; "
              f"shared QA service={args.qa_service_concurrency}, QA RPM={args.qa_rpm}, "
              f"Judge RPM={args.judge_rpm}, OpenRouter={args.openrouter_concurrency}/"
              f"{args.openrouter_rpm} RPM. Shared limits include other commands.")

    def _resources(self):
        endpoint = self.backend.endpoint() if self.backend.endpoint else _dashscope_base_http_api_url()
        qa_service = digest([endpoint, digest(self.api_key)])
        router = 'openrouter:' + digest([OPENROUTER_URL, digest(self.judge_key)])
        service = 'qa-service:' + qa_service
        qa_rate = 'qa-rpm:' + digest([qa_service, self.args.qa_model])
        judge_rate = 'judge-rpm:' + digest([router, AUTHOR_JUDGE_MODEL])
        self.resource_keys = {'qa': [service, qa_rate], 'judge': [router, judge_rate]}
        self.admission_roots = {'qa': service, 'judge': router}
        if self.args.qa_model == GEMINI_QA_MODEL:
            self.resource_keys['qa'].append(router)
            self.admission_roots['qa'] = router
        return {service: (self.args.qa_service_concurrency, 0), qa_rate: (0, self.args.qa_rpm),
                router: (self.args.openrouter_concurrency, self.args.openrouter_rpm),
                judge_rate: (0, self.args.judge_rpm)}

    def _owners(self, case, task):
        video = next((v for v in case['videos'] if v['video_id'] == task.video_id), None)
        context = video_case_context(case, video) if video is not None else case
        question = next(q for q in context['questions'] if q['question_id'] == task.question_id)
        return video, context, question

    def _records(self, case, task, result=None):
        video, _, question = self._owners(case, task)
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

    def _fingerprint(self, case, video, question, stage, mode, prefix, based):
        context = video_case_context(case, video) if video else case
        if stage:
            fp = stage_fingerprint(case, video, question, stage, prefix)
        elif mode == 'question_only':
            fp = stage_fingerprint(case, {'video_id': 'case'}, question, 'question_only', None)
        else:
            fp = qa_fingerprint(case, video, question, mode, prefix, based=based)
        binding = digest([fp, question_content(question), context['conflict_spec']])
        return fp, binding

    def _make(self, path, case, video, question, effort, kind, stage=None, result=None):
        mode = ('question_only' if stage == 'question_only' else 'video') if stage else self.args.input
        prefix = (effective_prefix(self.args.group, self.args.with_work_title_prefix)
                  if stage == 'control_video' else None if stage else
                  work_title_prefix_condition(self.args.group, mode, self.args.with_work_title_prefix))
        based = False if stage else bool(self.args.based)
        fp, binding = self._fingerprint(case, video, question, stage, mode, prefix, based)
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

    def _offer(self, pending, task):
        if task.key not in self.failed and task.path not in self.failed_cases:
            pending[task.key] = task

    def _error(self, key, message):
        if key not in self.failed:
            self.failed.add(key)
            print(f"Error: {message}", file=sys.stderr, flush=True)

    def note_cache(self, path, result, *, judged=False):
        identity = (path_key(path), result.get('run_id'))
        for kind in ('qa', 'judge') if judged else ('qa',):
            if identity not in self.produced_runs[kind]:
                self.cache_records[kind].add(identity)

    def plan_case(self, path, case, pending):
        from .evaluation import (_question_result_selected, _result_selected,
                                 _require_selected_final_answers, _require_selected_prefix_metadata)
        args = self.args
        if not self.filter_only:
            _require_selected_prefix_metadata([(path, case)], args=args, efforts=set(self.efforts))
            _require_selected_final_answers([(path, case)], args=args, efforts=set(self.efforts))
        if args.input == 'question_only':
            for q in selected_questions({**case, 'questions': require_question_only_compatible(case)},
                                        set(args.question_id or [])):
                for effort in self.efforts:
                    existing = [r for r in q.get('question_only_results', [])
                                if qa_result_key(r) == qa_run_key('question_only', q['question_id'], args.qa_model, effort)]
                    if not existing:
                        self._offer(pending, self._make(path, case, None, q, effort, 'qa'))
                    for r in existing:
                        self.note_cache(path, r, judged=r.get('judgment') is not None)
                        if _question_result_selected(q, r, args=args, efforts=set(self.efforts)) and r.get('judgment') is None:
                            self._offer(pending, self._make(path, case, None, q, effort, 'judge', result=r))
            return
        for video in eligible_videos(case, input_mode=args.input, selected_video_ids=set(args.video_id or []),
                                     video_scope=args.video_scope, based=args.based):
            context = video_case_context(case, video)
            for q in selected_questions(context, set(args.question_id or [])):
                for effort in self.efforts:
                    passed = True
                    if not self.main_only:
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
                                self._error(str(slot), f"Filter unavailable {case['case_id']}/{q['question_id']}: {state['reason']}")
                                passed = False
                                break
                            if force_qa or state['status'] in ('missing', 'stale'):
                                self._offer(pending, self._make(path, case, video, q, effort, 'qa', stage))
                                passed = False
                                break
                            if force_judge or state['status'] == 'unjudged':
                                self._offer(pending, self._make(path, case, video, q, effort, 'judge', stage, state['result']))
                                passed = False
                                break
                            if state['status'] == 'failed':
                                passed = False
                                break
                    if self.filter_only:
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
                        self._offer(pending, self._make(path, case, video, q, effort, 'qa'))
                    for r in existing:
                        self.note_cache(path, r, judged=judgment_is_current(case, video, r))
                        if not r.get('final_answer'):
                            raise PipelineError("Selected QA has no final_answer; run --force-qa")
                        if _result_selected(video, r, args=args, efforts=set(self.efforts)) and not judgment_is_current(case, video, r):
                            # Let the filter's Judge own its latest authoritative record.
                            if video['role'] == 'control' and not passed:
                                continue
                            self._offer(pending, self._make(path, case, video, q, effort, 'judge', result=r))

    def plan(self):
        pending = {}
        for path, case in self.cases.items():
            if path in self.failed_cases:
                continue
            try:
                if path in self.dirty:
                    planned = {}
                    self.plan_case(path, case, planned)
                    self.case_plans[path] = planned
                    self.dirty.discard(path)
                pending.update({k: t for k, t in self.case_plans.get(path, {}).items() if k not in self.failed})
            except (PipelineError, OSError, KeyError, StopIteration) as exc:
                self.failed_cases.add(path)
                self._error(str(path), f"{path}: {exc}")
        return pending

    def needed(self, case, task):
        video, _, q = self._owners(case, task)
        fp, binding = self._fingerprint(case, video, q, task.stage, task.mode, task.prefix, task.based)
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
        records = self._records(case, task)
        if task.kind == 'qa':
            return not any(qa_result_key(r, include_work_title_prefix=task.prefix is not None) ==
                           qa_run_key(task.mode, q['question_id'], self.args.qa_model, task.effort,
                                      based=task.based, work_title_prefix=task.prefix)
                           and (task.mode == 'question_only' or qa_is_current(case, video, r)) for r in records)
        r = next((r for r in records if r.get('run_id') == task.result['run_id']), None)
        return r is not None and (r.get('judgment') is None if task.mode == 'question_only'
                                  else not judgment_is_current(case, video, r))

    def normalize_filter(self, case, task, result):
        video, _, q = self._owners(case, task)
        set_filter_field(result, 'stage', task.stage)
        set_filter_field(result, 'fingerprint', task.fingerprint)
        if task.stage == 'control_video' and scope_id(video) == 'case':
            result['input_fingerprint'] = qa_fingerprint(case, control_video(case, video), q, 'video', task.prefix)
        records = self._records(case, task, result)
        records[:] = [r for r in records if r.get('run_id') != result['run_id']]
        records.append(result)

    def claim(self, task):
        if task.token:
            return 'owned'
        with case_lock(task.path):
            case = load_case(task.path)
            if not self.needed(case, task):
                self.cases[task.path] = case
                self.dirty.add(task.path)
                self.cached.add(task.key)
                return 'cached'
            state, value = self.runtime.claim(task.key)
            if state == 'failed':
                self._error(task.key, f"Shared task failed {task.path.stem}/{task.question_id}: {value}")
            if state == 'owned':
                task.token = value
                if task.kind == 'judge' and task.stage:
                    result = copy.deepcopy(task.result)
                    result['judgment'] = None
                    self.normalize_filter(case, task, result)
                    atomic_write_json(task.path, case)
                    self.runtime.changed(task.path)
                    self.cases[task.path] = case
                    self.dirty.add(task.path)
            return state

    def ensure_backend(self):
        if not self.backend_ready:
            preflight = argparse.Namespace(**{**vars(self.args), 'input': 'question_only'})
            self.served = preflight_qa_backend(preflight)
            self.api_key = self.backend.require_api_key()
            if self.args.qa_model == QWEN_QA_MODEL:
                _require_dashscope_sdk().base_http_api_url = _dashscope_base_http_api_url()
            self.backend_ready = True

    def encode(self, task):
        if self.args.qa_model == QWEN_QA_MODEL:
            return _qwen_video_uri(task.video_path)
        if self.args.qa_model in LOCAL_QA_CONFIGS:
            return _local_video_uri(task.video_path, self.backend.service)
        return self.backend.encode_video(task.video_path)

    def prepare(self, task, pool):
        if task.kind != 'qa' or task.video_path is None:
            return True
        if task.prepared is not None:
            return True
        if task.media_key in self.media:
            task.prepared = self.media[task.media_key]
            self.media.move_to_end(task.media_key)
            return True
        future = self.preparing.get(task.media_key)
        if future is None:
            if len(self.preparing) >= 2:
                return False
            self.preparing[task.media_key] = pool.submit(self.encode, task)
            return False
        if not future.done():
            return False
        del self.preparing[task.media_key]
        task.prepared = future.result()
        self.media[task.media_key] = task.prepared
        self.media_bytes += len(task.prepared)
        self.trim_media()
        return True

    def trim_media(self):
        pinned = {key for key, count in self.media_active.items() if count}
        pinned.update(t.media_key for t in self.tasks.values() if t.prepared is not None)
        idle_bytes = sum(len(value) for key, value in self.media.items() if key not in pinned)
        for key in list(self.media):
            if key in pinned:
                continue
            size = len(self.media[key])
            if idle_bytes > self.media_budget or size > self.media_budget:
                del self.media[key]
                self.media_bytes -= size
                idle_bytes -= size

    def release_media(self, task):
        if task.media_key:
            self.media_active[task.media_key] -= 1
            if self.media_active[task.media_key] <= 0:
                del self.media_active[task.media_key]
            self.trim_media()

    def request(self, task, media):
        if task.kind == 'qa':
            results, _ = run_qa_batch(
                input_mode=task.mode, video_path=task.video_path, context_text=task.context_text,
                work_title=task.context['title'].split(':', 1)[0].strip() if task.prefix else None,
                work_title_prefix=task.prefix, question_runs=[(task.question, task.effort)],
                qa_model=self.args.qa_model, api_key=self.api_key, timeout=self.args.timeout,
                max_retries=0, request_limiter=None, local_served_model_id=self.served,
                local_max_tokens=local_qa_max_tokens(self.args), based=task.based,
                diagnostics=self.diagnostics, single_attempt=True, prepared_video_input=media,
                diagnostic_stage=('question_only filter' if task.stage == 'question_only' else
                                  'control filter' if task.stage == 'control_video' else 'main'))
            return results[0]
        from .evaluation import JUDGE_SYSTEM_PROMPT
        q, facts = task.question, task.context['conflict_spec']
        final_answer = task.result.get('final_answer')
        if not isinstance(final_answer, str) or not final_answer.strip():
            raise PipelineError('Selected QA has no final_answer; run --force-qa')
        payload = {'video_role': task.context['role'], 'question': q['text_en'], 'final_answer': final_answer,
                   'normal_fact': facts['normal_fact_en'], 'intended_video_fact': facts['intended_video_fact_en'],
                   'conflict_video_reference': q['conflict_video_reference_en'],
                   'normal_control_reference': q['normal_control_reference_en']}
        verdict, response = openrouter_json(
            messages=[{'role': 'system', 'content': JUDGE_SYSTEM_PROMPT},
                      {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            model=AUTHOR_JUDGE_MODEL, schema_name='knowledge_conflict_judgment', schema=JUDGMENT_SCHEMA,
            api_key=self.judge_key, timeout=self.args.timeout, single_attempt=True)
        if verdict.get('verdict') not in VERDICTS:
            raise PipelineError('Invalid judgment verdict')
        if task.context['role'] == 'control' and verdict['verdict'] == 'knowledge_trapped':
            raise PipelineError('Judge returned knowledge_trapped for a control input')
        if task.stage and verdict['verdict'] not in ('context_grounded', 'ambiguous_or_unjudgeable'):
            raise PipelineError('Invalid filter judgment verdict')
        confidence = float(verdict['confidence'])
        if not 0 <= confidence <= 1:
            raise PipelineError('Invalid judgment confidence')
        return {**verdict, 'confidence': confidence, 'timestamp': utc_now(),
                'judge_model': AUTHOR_JUDGE_MODEL, 'judge_request_id': response.get('id')}

    def merge(self, case, task, output):
        video, _, q = self._owners(case, task)
        _, binding = self._fingerprint(case, video, q, task.stage, task.mode, task.prefix, task.based)
        if binding != task.binding:
            raise PipelineError('Inputs changed during request; refusing stale result')
        if task.kind == 'qa':
            if task.stage:
                self.normalize_filter(case, task, output)
            else:
                if task.mode != 'question_only':
                    output['input_fingerprint'] = task.fingerprint
                else:
                    # Same request as the shared question-only filter: persist its
                    # existing provenance fields so another command can reuse it.
                    set_filter_field(output, 'stage', 'question_only')
                    set_filter_field(output, 'fingerprint', task.fingerprint)
                self._records(case, task).append(output)
            return
        records = self._records(case, task, task.result)
        result = next((r for r in records if r.get('run_id') == task.result['run_id']), None)
        if result is None or result.get('final_answer') != task.result.get('final_answer'):
            raise PipelineError('QA changed during judging; refusing stale judgment')
        if task.stage:
            output['filter_fingerprint'] = digest({'input': task.fingerprint, 'final_answer': result['final_answer']})
            if task.stage == 'control_video' and scope_id(video) == 'case':
                output['input_fingerprint'] = judgment_fingerprint(case, control_video(case, video), result)
        elif task.mode != 'question_only':
            output['input_fingerprint'] = judgment_fingerprint(case, video, result)
        if not task.stage and filter_field(result, 'stage'):
            output['filter_fingerprint'] = digest({'input': filter_field(result, 'fingerprint'),
                                                   'final_answer': result['final_answer']})
        result['judgment'] = output

    def fail(self, task, exc, *, write=False):
        task.prepared = None
        self.trim_media()
        self._error(task.key, f"{task.path.stem}/{task.question_id}/{task.stage or 'main'}/{task.kind}: {exc}")
        if task.token and self.runtime.owns(task.key, task.token):
            self.runtime.finish(task.key, task.token, str(exc))
        self.main_reservations.discard((task.path, task.video_id, task.question_id, task.effort))
        if write:
            self.failed_cases.add(task.path)

    def ordered(self, tasks, kind):
        groups = {True: defaultdict(deque), False: defaultdict(deque)}
        for t in tasks:
            groups[bool(t.stage)][t.path].append(t)
        order = []
        tick = self.ticks[kind]
        while any(groups.values()):
            filt = tick % 4 != 3
            if not groups[filt]:
                filt = not filt
            cases = groups[filt]
            paths = sorted(cases, key=str)
            last = self.last_case.get((kind, filt))
            chosen = next((p for p in paths if last is None or str(p) > str(last)), paths[0])
            task = cases[chosen].popleft()
            if not cases[chosen]:
                del cases[chosen]
            order.append(task)
            tick += 1
        return order

    def run(self, *, filter_only=False, main_only=False):
        self.filter_only, self.main_only = filter_only, main_only
        self.dirty.update(self.cases)
        inflight = {}
        last_log = time.monotonic()
        last_refresh = 0
        interrupted = False
        with ThreadPoolExecutor(max_workers=self.args.qa_concurrency) as qa_pool, \
             ThreadPoolExecutor(max_workers=self.args.judge_concurrency) as judge_pool, \
             ThreadPoolExecutor(max_workers=2) as media_pool:
            pools = {'qa': qa_pool, 'judge': judge_pool}
            try:
                while True:
                    self.runtime.check()
                    for future in list(inflight):
                        if not future.done():
                            continue
                        task, permit = inflight.pop(future)
                        self.release_media(task)
                        try:
                            output = future.result()
                        except Exception as exc:
                            retry = isinstance(exc, TransportError) and _is_retryable(exc) and task.attempts <= self.args.max_retries
                            delay = max(min(30, 2 ** (task.attempts - 1)) + random.uniform(0, .5),
                                        getattr(exc, 'retry_after', None) or 0)
                            keys = self.resource_keys[task.kind] if 'http 429' in str(exc).lower() else ()
                            self.runtime.release(permit, cooldown_keys=keys, delay=delay)
                            if retry:
                                task.due = time.monotonic() + delay
                                print(f"Retry {task.path.stem}/{task.question_id}/{task.kind} in {delay:.1f}s", flush=True)
                            else:
                                self.fail(task, exc)
                            continue
                        self.runtime.release(permit)
                        try:
                            if task.path in self.failed_cases:
                                raise PipelineError('Case was stopped after a prior write failure')
                            self.cases[task.path] = self.runtime.commit(
                                task.path, task.key, task.token, lambda case: self.merge(case, task, output))
                            self.completed[task.kind] += 1
                            self.produced_runs[task.kind].add((path_key(task.path),
                                output['run_id'] if task.kind == 'qa' else task.result['run_id']))
                            self.dirty.add(task.path)
                            if task.force_slot:
                                self.forced.add(task.force_slot)
                            if task.kind == 'judge':
                                self.main_reservations.discard((task.path, task.video_id, task.question_id, task.effort))
                            print(f"{task.kind.upper()} {task.path.stem}/{task.video_id or 'case'}/"
                                  f"{task.question_id}/{task.effort}/{task.stage or 'main'} saved", flush=True)
                        except Exception as exc:
                            self.fail(task, exc, write=True)
                    now = time.monotonic()
                    if now - last_refresh >= 1:
                        versions = self.runtime.versions()
                        for path in self.cases:
                            if versions.get(path_key(path)) != self.versions.get(path_key(path)):
                                self.cases[path] = load_case(path)
                                self.dirty.add(path)
                        self.versions = versions
                        last_refresh = now
                    pending = self.plan()
                    self.waiting_keys.intersection_update(pending)
                    if pending:
                        self.judge_key = require_openrouter_api_key()
                    active_keys = {t.key for t, _ in inflight.values()}
                    progressed = False
                    active_counts = Counter(t.kind for t, _ in inflight.values())
                    order = ('qa', 'judge') if self.next_pool == 0 else ('judge', 'qa')
                    self.next_pool = 1 - self.next_pool
                    # One admission per pool per pass preserves QA/Judge alternation.
                    waiting_resources = set()
                    for kind in order:
                        capacity = getattr(self.args, kind + '_concurrency')
                        if active_counts[kind] >= capacity:
                            continue
                        candidates = [t for t in pending.values() if t.kind == kind and t.key not in active_keys]
                        for task in self.ordered(candidates, kind):
                            if task.due > now:
                                continue
                            reservation = (task.path, task.video_id, task.question_id, task.effort)
                            if kind == 'qa' and not task.stage and reservation not in self.main_reservations:
                                judges = [t for t in pending.values() if t.kind == 'judge' and not t.stage]
                                slots = {(t.path, t.video_id, t.question_id, t.effort) for t in judges}
                                backlog = len(judges) + len(self.main_reservations - slots)
                                if backlog >= max(64, 4 * self.args.judge_concurrency):
                                    continue
                            try:
                                if kind == 'qa':
                                    self.ensure_backend()
                                if not self.prepare(task, media_pool):
                                    continue
                                try:
                                    state = self.claim(task)
                                except Exception as exc:
                                    self.fail(task, exc, write=True)
                                    continue
                                if state == 'waiting':
                                    self.waiting_keys.add(task.key)
                                    task.prepared = None
                                    self.trim_media()
                                    continue
                                self.waiting_keys.discard(task.key)
                                if state in ('cached', 'failed'):
                                    task.prepared = None
                                    self.trim_media()
                                    progressed = True
                                    continue
                                waiting_resources.update(self.resource_keys[kind])
                                permit = self.runtime.reserve(self.resource_keys[kind], self.args.timeout,
                                                              lane=kind, fairness_key=self.admission_roots[kind])
                                if permit is None:
                                    break
                                task.attempts += 1
                                self.attempts[kind] += 1
                                try:
                                    future = pools[kind].submit(self.request, task, task.prepared)
                                except BaseException:
                                    self.runtime.release(permit)
                                    raise
                                task.prepared = None
                                if task.media_key:
                                    self.media_active[task.media_key] += 1
                                inflight[future] = (task, permit)
                                if kind == 'qa' and not task.stage:
                                    self.main_reservations.add(reservation)
                                self.ticks[kind] += 1
                                self.last_case[(kind, bool(task.stage))] = task.path
                                progressed = True
                                break
                            except Exception as exc:
                                self.fail(task, exc, write=isinstance(exc, OSError))
                    self.runtime.withdraw(set(self.resources) - waiting_resources)
                    if now - last_log >= 10:
                        retrying = sum(t.due > now for t in pending.values())
                        elapsed = max(1, now - self.started)
                        limits = [{'resource': r['key'].split(':')[0], 'active': r['active'],
                                   'capacity': r['capacity'], 'rpm': r['rpm'],
                                   'wait_seconds': round(max(0, r['next_start'] - time.time(), r['cooldown'] - time.time()), 1)}
                                  for r in self.runtime.occupancy()]
                        ready = sum(t.key not in active_keys and t.key not in self.waiting_keys and t.due <= now
                                    for t in pending.values())
                        cached_counts = {k: len(v) for k, v in self.cache_records.items()}
                        print(f"Progress ready={ready} in_flight={len(inflight)} other_process={len(self.waiting_keys)} "
                              f"retry={retrying} saved={dict(self.completed)} requests={dict(self.attempts)} "
                              f"cached={cached_counts} rate={sum(self.completed.values()) / elapsed:.2f}/s "
                              f"shared={json.dumps(limits)}", flush=True)
                        last_log = now
                    if not pending and not inflight:
                        break
                    if not progressed:
                        time.sleep(.1)
            except KeyboardInterrupt:
                interrupted = True
                self.interrupted = True
                print('Interrupted: stopping admission; saving completed in-flight responses.', file=sys.stderr)
            finally:
                # No new submissions here. Preserve responses already paid for, even on interruption.
                for future, (task, permit) in inflight.items():
                    try:
                        output = future.result()
                        self.runtime.commit(task.path, task.key, task.token,
                                            lambda case, t=task, out=output: self.merge(case, t, out))
                    except Exception as exc:
                        self.fail(task, exc)
                    finally:
                        self.release_media(task)
                        self.runtime.release(permit)
                self.runtime.withdraw(self.resources)
                self.preparing.clear()
        if self.args.input != 'question_only' and not main_only:
            counts = Counter()
            for path, case in self.cases.items():
                if path in self.failed_cases:
                    continue
                seen = set()
                for video in eligible_videos(case, input_mode=self.args.input,
                        selected_video_ids=set(self.args.video_id or []),
                        video_scope=self.args.video_scope, based=self.args.based):
                    for q in selected_questions(video_case_context(case, video), set(self.args.question_id or [])):
                        for effort in self.efforts:
                            key = (scope_id(video), q['question_id'], effort)
                            if key not in seen:
                                seen.add(key)
                                gate = question_gate(case, video, q, self.args.qa_model, effort,
                                    effective_prefix(self.args.group, self.args.with_work_title_prefix))
                                counts[gate['reason']] += 1
            print('Question filter gates: ' + json.dumps(dict(counts), sort_keys=True))
        return 1 if interrupted or self.failed else 0


def command_qa_judge(args):
    from .evaluation import (_completion_counts, _preflight_cases, _preclear_force,
                             _require_selected_final_answers, _require_selected_prefix_metadata,
                             _qa_completed_from_loaded)
    paths = iter_case_paths(grouped_dir(args.dataset_dir, args.group), args.case_id)
    efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
    diagnostics = QADiagnostics(include_truncation=args.qa_model in LOCAL_QA_CONFIGS)
    try:
        with Runtime(paths, exclusive=args.force_qa or args.force_judge) as runtime:
            loaded, total = _preflight_cases(args, efforts, enforce_gate=False)
            if not total:
                print('No eligible question/video targets in the selected scope.')
                return 0
            # Global format/metadata checks must precede ordinary model work.
            if not args.force_qa and not args.filter_only:
                _require_selected_prefix_metadata(loaded, args=args, efforts=set(efforts))
                _require_selected_final_answers(loaded, args=args, efforts=set(efforts))
            engine = Engine(args, runtime, loaded, diagnostics)
            status = 0
            if args.filter_only:
                return engine.run(filter_only=True)
            if args.force_qa or args.force_judge:
                if args.input != 'question_only':
                    status = engine.run(filter_only=True)
                    if engine.interrupted:
                        return 1
                loaded, total = _preflight_cases(args, efforts)
                if not total:
                    print('No questions passed the required filter gates in the selected scope.')
                    return status
                if not args.force_qa:
                    _require_selected_prefix_metadata(loaded, args=args, efforts=set(efforts))
                    _require_selected_final_answers(loaded, args=args, efforts=set(efforts))
                require_openrouter_api_key()
                qa_done = _qa_completed_from_loaded(loaded, args=args, efforts=efforts)
                if args.force_qa or qa_done != total:
                    engine.served = preflight_qa_backend(args, loaded)
                # Exclusive registration prevents concurrent writers; still use the
                # same ordered file locks as snapshots and ordinary commits.
                from contextlib import ExitStack
                with ExitStack() as stack:
                    for path in sorted(paths, key=path_key):
                        stack.enter_context(case_lock(path))
                    _preclear_force(loaded, args=args, efforts=set(efforts))
                    for path in paths:
                        runtime.changed(path)
                engine.cases = dict(loaded)
                status |= engine.run(main_only=True)
            else:
                status = engine.run()
            snapshot = runtime.snapshot(paths)
            done, total, judged, judge_total = _completion_counts(args, efforts, snapshot=snapshot)
            incomplete = done != total or judged != judge_total
            if args.input == 'video':
                done, total, judged, judge_total = _completion_counts(args, efforts, include_control=False, snapshot=snapshot)
            print(f'QA: {done}/{total}\nJudge: {judged}/{judge_total}')
            print(f'This run: requests={dict(engine.attempts)}, saved={dict(engine.completed)}, '
                  f'cached={ {k: len(v) for k, v in engine.cache_records.items()} }, '
                  f'concurrently reused={len(engine.cached)}')
            return 1 if status or incomplete else 0
    finally:
        diagnostics.print_summary()
