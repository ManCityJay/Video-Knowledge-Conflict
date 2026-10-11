"""Request scheduling, task claims, shared admission, delayed retries and progress."""
from __future__ import annotations

import copy
import json
import random
import sys
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

from .common import PipelineError, video_case_context
from .filters import effective_prefix, question_gate, scope_id
from .integrity import digest
from .media_cache import MediaCache
from .paths import grouped_dir, iter_case_paths
from .qa import LOCAL_QA_CONFIGS, preflight_qa_backend, qa_service_endpoint
from .qa_diagnostics import QADiagnostics
from .result_rules import expand_thinking_efforts
from .runtime import Runtime, case_lock, path_key
from .selection import eligible_videos, selected_questions
from .settings import AUTHOR_JUDGE_MODEL, GEMINI_QA_MODEL
from .storage import atomic_write_json, load_case
from .task_execution import TaskExecutor
from .task_planning import TaskPlanner
from .transport import OPENROUTER_URL, TransportError, is_retryable, require_openrouter_api_key


class Engine:
    def __init__(self, args, runtime, loaded, diagnostics):
        self.args, self.runtime, self.diagnostics = args, runtime, diagnostics
        self.cases = dict(loaded)
        self.efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
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
        self.planner = TaskPlanner(args, runtime, self.failed, self.failed_cases,
                                   self.forced, self.note_cache, self._error)
        self.execution = TaskExecutor(args, self.planner, diagnostics)
        self.media_cache = MediaCache(args.qa_model, self.planner.tasks)
        self.started = time.monotonic()
        self.interrupted = False
        self.resources = self._resources()
        self.runtime.configure(self.resources)
        print(f"Concurrency: QA={args.qa_concurrency}, Judge={args.judge_concurrency}; "
              f"shared QA service={args.qa_service_concurrency}, QA RPM={args.qa_rpm}, "
              f"Judge RPM={args.judge_rpm}, OpenRouter={args.openrouter_concurrency}/"
              f"{args.openrouter_rpm} RPM. Shared limits include other commands.")

    def _resources(self):
        endpoint = qa_service_endpoint(self.args.qa_model)
        qa_service = digest([endpoint, digest(self.execution.api_key)])
        router = 'openrouter:' + digest([OPENROUTER_URL, digest(self.execution.judge_key)])
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


    def _error(self, key, message):
        if key not in self.failed:
            self.failed.add(key)
            print(f"Error: {message}", file=sys.stderr, flush=True)

    def note_cache(self, path, result, *, judged=False):
        identity = (path_key(path), result.get('run_id'))
        for kind in ('qa', 'judge') if judged else ('qa',):
            if identity not in self.produced_runs[kind]:
                self.cache_records[kind].add(identity)


    def plan(self):
        pending = {}
        for path, case in self.cases.items():
            if path in self.failed_cases:
                continue
            try:
                if path in self.dirty:
                    planned = {}
                    self.planner.plan_case(path, case, planned, filter_only=self.filter_only, main_only=self.main_only)
                    self.case_plans[path] = planned
                    self.dirty.discard(path)
                pending.update({k: t for k, t in self.case_plans.get(path, {}).items() if k not in self.failed})
            except (PipelineError, OSError, KeyError, StopIteration) as exc:
                self.failed_cases.add(path)
                self._error(str(path), f"{path}: {exc}")
        return pending


    def claim(self, task):
        if task.token:
            return 'owned'
        with case_lock(task.path):
            case = load_case(task.path)
            if not self.planner.needed(case, task):
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
                    self.execution.normalize_filter(case, task, result)
                    atomic_write_json(task.path, case)
                    self.runtime.changed(task.path)
                    self.cases[task.path] = case
                    self.dirty.add(task.path)
            return state


    def fail(self, task, exc, *, write=False):
        task.prepared = None
        self.media_cache.trim()
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
                        self.media_cache.release(task)
                        try:
                            output = future.result()
                        except Exception as exc:
                            retry = isinstance(exc, TransportError) and is_retryable(exc) and task.attempts <= self.args.max_retries
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
                                task.path, task.key, task.token, lambda case: self.execution.merge(case, task, output))
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
                        self.execution.judge_key = require_openrouter_api_key()
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
                                    self.execution.ensure_backend()
                                if not self.media_cache.prepare(task, media_pool):
                                    continue
                                try:
                                    state = self.claim(task)
                                except Exception as exc:
                                    self.fail(task, exc, write=True)
                                    continue
                                if state == 'waiting':
                                    self.waiting_keys.add(task.key)
                                    task.prepared = None
                                    self.media_cache.trim()
                                    continue
                                self.waiting_keys.discard(task.key)
                                if state in ('cached', 'failed'):
                                    task.prepared = None
                                    self.media_cache.trim()
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
                                    future = pools[kind].submit(self.execution.request, task, task.prepared)
                                except BaseException:
                                    self.runtime.release(permit)
                                    raise
                                task.prepared = None
                                self.media_cache.pin(task)
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
                                            lambda case, t=task, out=output: self.execution.merge(case, t, out))
                    except Exception as exc:
                        self.fail(task, exc)
                    finally:
                        self.media_cache.release(task)
                        self.runtime.release(permit)
                self.runtime.withdraw(self.resources)
                self.media_cache.clear_preparing()
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
    from .evaluation import (
        completion_counts,
        preflight_cases,
        preclear_force,
        require_selected_final_answers,
        require_selected_prefix_metadata,
        qa_completed_from_loaded,
    )
    paths = iter_case_paths(grouped_dir(args.dataset_dir, args.group), args.case_id)
    efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
    diagnostics = QADiagnostics(include_truncation=args.qa_model in LOCAL_QA_CONFIGS)
    try:
        with Runtime(paths, exclusive=args.force_qa or args.force_judge) as runtime:
            loaded, total = preflight_cases(args, efforts, enforce_gate=False)
            if not total:
                print('No eligible question/video targets in the selected scope.')
                return 0
            # Global format/metadata checks must precede ordinary model work.
            if not args.force_qa and not args.filter_only:
                require_selected_prefix_metadata(loaded, args=args, efforts=set(efforts))
                require_selected_final_answers(loaded, args=args, efforts=set(efforts))
            engine = Engine(args, runtime, loaded, diagnostics)
            status = 0
            if args.filter_only:
                return engine.run(filter_only=True)
            if args.force_qa or args.force_judge:
                if args.input != 'question_only':
                    status = engine.run(filter_only=True)
                    if engine.interrupted:
                        return 1
                loaded, total = preflight_cases(args, efforts)
                if not total:
                    print('No questions passed the required filter gates in the selected scope.')
                    return status
                if not args.force_qa:
                    require_selected_prefix_metadata(loaded, args=args, efforts=set(efforts))
                    require_selected_final_answers(loaded, args=args, efforts=set(efforts))
                require_openrouter_api_key()
                qa_done = qa_completed_from_loaded(loaded, args=args, efforts=efforts)
                if args.force_qa or qa_done != total:
                    engine.execution.served = preflight_qa_backend(args, loaded)
                # Exclusive registration prevents concurrent writers; still use the
                # same ordered file locks as snapshots and ordinary commits.
                from contextlib import ExitStack
                with ExitStack() as stack:
                    for path in sorted(paths, key=path_key):
                        stack.enter_context(case_lock(path))
                    preclear_force(loaded, args=args, efforts=set(efforts))
                    for path in paths:
                        runtime.changed(path)
                engine.cases = dict(loaded)
                status |= engine.run(main_only=True)
            else:
                status = engine.run()
            snapshot = runtime.snapshot(paths)
            done, total, judged, judge_total = completion_counts(args, efforts, snapshot=snapshot)
            incomplete = done != total or judged != judge_total
            if args.input == 'video':
                done, total, judged, judge_total = completion_counts(args, efforts, include_control=False, snapshot=snapshot)
            print(f'QA: {done}/{total}\nJudge: {judged}/{judge_total}')
            print(f'This run: requests={dict(engine.attempts)}, saved={dict(engine.completed)}, '
                  f'cached={ {k: len(v) for k, v in engine.cache_records.items()} }, '
                  f'concurrently reused={len(engine.cached)}')
            return 1 if status or incomplete else 0
    finally:
        diagnostics.print_summary()
