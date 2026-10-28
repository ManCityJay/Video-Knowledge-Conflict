"""Independent Judge queue with main-pipeline shared admission and retries."""
from __future__ import annotations

import copy
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor

from vconflict_pipeline.common import PipelineError, utc_now
from vconflict_pipeline.integrity import digest
from vconflict_pipeline.judging import judge_answer
from vconflict_pipeline.runtime import Runtime
from vconflict_pipeline.settings import AUTHOR_JUDGE_MODEL
from vconflict_pipeline.transport import OPENROUTER_URL, TransportError, is_retryable
from .storage import judge_key, mutate_case, records_for


class JudgeQueue:
    def __init__(self, args, paths, run_id):
        self.args, self.run_id = args, run_id
        self.key = os.environ.get('OPENROUTER_API_KEY', '').strip()
        if not self.key:
            raise PipelineError('OPENROUTER_API_KEY is required for pending Judge requests')
        self.runtime = Runtime(paths)
        router = 'openrouter:' + digest([OPENROUTER_URL, digest(self.key)])
        rate = 'judge-rpm:' + digest([router, AUTHOR_JUDGE_MODEL])
        self.keys, self.root = [router, rate], router
        try:
            self.runtime.configure({router: (args.openrouter_concurrency, args.openrouter_rpm),
                                    rate: (0, args.judge_rpm)})
            self.pool = ThreadPoolExecutor(max_workers=args.judge_concurrency, thread_name_prefix='vcd-judge')
        except BaseException:
            self.runtime.__exit__(None, None, None)
            raise
        self.futures = []
        self.counts = {'executed': 0, 'saved': 0, 'failed': 0, 'network_retries': 0}
        self.mutex, self.stop = threading.Lock(), threading.Event()

    def count(self, key):
        with self.mutex:
            self.counts[key] += 1

    def submit(self, path, target, result):
        self.futures.append(self.pool.submit(self.work, path, copy.deepcopy(target), copy.deepcopy(result)))

    def work(self, path, target, result):
        key = judge_key(target, result)
        error = None
        for attempt in range(self.args.max_retries + 1):
            if self.stop.is_set():
                return
            permit = None
            try:
                while permit is None:
                    self.runtime.check()
                    if self.stop.wait(.05):
                        return
                    permit = self.runtime.reserve(self.keys, self.args.timeout,
                                                  lane=target['label'] + result['method'], fairness_key=self.root)
                self.count('executed')
                judgment = judge_answer(
                    question=target['question'], facts=target['context']['conflict_spec'], role='conflict',
                    final_answer=result['final_answer'], api_key=self.key, timeout=self.args.timeout)
                self.runtime.release(permit)
                permit = None
                judgment.update(judge_key=key, run_id=self.run_id)
                def save(case):
                    record = next(r for r in records_for(case, target) if r['qa_id'] == result['qa_id'])
                    if judge_key(target, record) != key or record.get('invalidated_at'):
                        raise PipelineError('QA changed during judging')
                    record['judgment'] = judgment
                    record.pop('judge_error', None)
                mutate_case(path, save)
                self.count('saved')
                print(f"Judge: saved {target['label']}/{result['method']} {judgment['verdict']}", flush=True)
                return
            except Exception as exc:
                error = {'type': type(exc).__name__, 'message': str(exc)[:1000],
                         'timestamp': utc_now(), 'run_id': self.run_id, 'judge_key': key}
                delay = max(min(30, 2**attempt) + random.uniform(0, .5),
                            getattr(exc, 'retry_after', None) or 0)
                if permit is not None:
                    self.runtime.release(permit, cooldown_keys=self.keys if 'http 429' in str(exc).lower() else (),
                                         delay=delay)
                if isinstance(exc, TransportError) and is_retryable(exc) and attempt < self.args.max_retries:
                    self.count('network_retries')
                    if self.stop.wait(delay):
                        return
                    continue
                break
        def save_error(case):
            record = next(r for r in records_for(case, target) if r['qa_id'] == result['qa_id'])
            record['judge_error'] = error
        mutate_case(path, save_error)
        self.count('failed')
        print(f"Judge: failed {target['label']}/{result['method']}: {error['message']}", flush=True)

    def close(self, *, cancel=False):
        if cancel:
            self.stop.set()
        self.pool.shutdown(wait=True, cancel_futures=cancel)
        try:
            for future in self.futures:
                if not future.cancelled():
                    future.result()
        finally:
            self.runtime.__exit__(None, None, None)
