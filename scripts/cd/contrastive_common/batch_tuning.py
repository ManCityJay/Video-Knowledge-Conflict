"""Online batch-ceiling search using real inference, without changing QA budgets."""
from __future__ import annotations

import math
from pathlib import Path

from vconflict_pipeline.common import utc_now
from .storage import atomic_json, digest_json, make_config, read_json


class BatchMemoryPressure(RuntimeError):
    """Split a multi-sample batch before allocator retries dominate throughput."""


class BatchTuner:
    def __init__(self, args):
        import torch
        self.args = args
        self.path = args.output / 'batch_tuning.json'
        self.control = args.output / 'batch_control.json'
        self.base_bytes = torch.cuda.memory_allocated(args.device)
        self.total_bytes = torch.cuda.get_device_properties(args.device).total_memory
        self.hard_cap = args.max_batch_size
        candidates = [n for n in (1, 2, 4, 6, 8, 12, 16, 24, 32) if n <= self.hard_cap]
        if self.hard_cap not in candidates:
            candidates.append(self.hard_cap)
        candidates.sort()
        config = make_config(args)
        key = digest_json({k: config[k] for k in (
            'model_family', 'model_path', 'method', 'dtype', 'max_new_tokens',
            'thinking_token_budget', 'thinking_effort', 'alpha', 'beta', 'based',
            'sampling', 'season', 'selection')} | {'tuner_protocol': 1, 'candidates': candidates})
        self.state = {
            'profile_key': key, 'method': args.method, 'model_family': args.model_family,
            'status': 'exploring', 'plan': candidates + list(reversed(candidates)),
            'trial': 0, 'trial_batches': 0, 'trial_tokens': 0, 'partial_batches': 0,
            'stats': {}, 'blocked_at': None, 'skipped': [], 'selected_batch_size': None,
            'started_at': utc_now(), 'selection_metric': 'effective_generated_tokens_per_wall_second',
            'comparison': 'Online production samples differ; selected size is best observed, not a controlled global optimum.'}
        if self.path.exists():
            old = read_json(self.path)
            if old.get('profile_key') == key:
                self.state = old
        self._advance_unsafe()
        self.save()

    def save(self):
        self.state['updated_at'] = utc_now()
        self.state['base_allocated_bytes'] = self.base_bytes
        self.state['device_total_bytes'] = self.total_bytes
        for record in self.state['stats'].values():
            wall = record['wall_seconds'] + record['failed_wall_seconds']
            record['effective_tokens_per_second'] = record['generated_tokens'] / wall if wall else None
            record['decoded_samples_per_hour'] = record['samples'] * 3600 / wall if wall else None
        atomic_json(self.path, self.state)

    def record(self, size):
        return self.state['stats'].setdefault(str(size), {
            'successful_batches': 0, 'samples': 0, 'generated_tokens': 0,
            'wall_seconds': 0., 'failed_wall_seconds': 0., 'ooms': 0,
            'peak_allocated_bytes': 0, 'max_generated_length': 0})

    def memory_safe(self, size):
        if size == 1:
            return True
        blocked = self.state['blocked_at']
        if blocked is not None and size >= blocked:
            return False
        incremental = [max(0, r['peak_allocated_bytes'] - self.base_bytes) / int(n)
                       for n, r in self.state['stats'].items() if r['successful_batches']]
        if not incremental:
            return size <= 4
        return self.base_bytes + max(incremental) * size <= self.total_bytes * .90

    def best(self):
        candidates = []
        for size, r in self.state['stats'].items():
            n = int(size)
            if not r['successful_batches'] or not self.memory_safe(n):
                continue
            # Compare successful work against wall time INCLUDING failed attempts.
            rate = r['generated_tokens'] / max(1e-9, r['wall_seconds'] + r['failed_wall_seconds'])
            candidates.append((r['successful_batches'] >= 2, rate, -n))
        if not candidates:
            return 1
        # Prefer repeated evidence; ties within 3% favor a smaller, steadier batch.
        repeated = [r for r in candidates if r[0]]
        options = repeated or candidates
        maximum = max(r[1] for r in options)
        return min(-r[2] for r in options if r[1] >= maximum * .97)

    def _advance_unsafe(self):
        plan = self.state['plan']
        while self.state['trial'] < len(plan):
            size = plan[self.state['trial']]
            if self.memory_safe(size):
                self.state['current_batch_size'] = size
                return
            self.state['skipped'].append({'trial': self.state['trial'], 'size': size,
                                          'reason': 'memory_headroom_or_previous_failure'})
            self.state['trial'] += 1
        self.state.update(status='selected', selected_batch_size=self.best())
        self.state['current_batch_size'] = self.state['selected_batch_size']

    def desired(self):
        self._advance_unsafe()
        size = self.state['current_batch_size']
        if self.state['status'] == 'selected':
            size = self.best()
            self.state['selected_batch_size'] = size
            self.state['current_batch_size'] = size
        # A monitor may safely override the ceiling at a batch boundary.
        if self.control.exists():
            value = read_json(self.control).get('batch_size')
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= self.hard_cap:
                raise ValueError('batch_control.json batch_size must be an integer within the configured cap')
            size = value
        self.save()
        return size

    def observe(self, audit):
        if audit['phase'] != 'initial':
            recovery = self.state.setdefault('recovery', {'batches': 0, 'wall_seconds': 0., 'generated_tokens': 0})
            recovery['batches'] += 1
            recovery['wall_seconds'] += audit['wall_seconds']
            recovery['generated_tokens'] += audit['generated_tokens']
            self.save()
            return
        size = audit['batch_size']
        r = self.record(size)
        r['successful_batches'] += 1
        r['samples'] += size
        r['generated_tokens'] += audit['generated_tokens']
        r['wall_seconds'] += audit['wall_seconds']
        r['peak_allocated_bytes'] = max(r['peak_allocated_bytes'], audit['peak_allocated_bytes'])
        r['max_generated_length'] = max(r['max_generated_length'], audit.get('decode_steps', 0))
        # Recovery batches contribute to accounting, but do not advance the search.
        if audit['phase'] == 'initial' and self.state['status'] == 'exploring' and not self.control.exists():
            expected = self.state['current_batch_size']
            if size == expected:
                self.state['trial_batches'] += 1
                self.state['trial_tokens'] += audit['generated_tokens']
            else:
                self.state['partial_batches'] += 1
            enough = (self.state['trial_batches'] >= 2 and
                      (self.state['trial_tokens'] >= 512 or self.state['trial_batches'] >= 4))
            if enough or self.state['partial_batches'] >= 8:
                self.state['trial'] += 1
                self.state.update(trial_batches=0, trial_tokens=0, partial_batches=0)
                self._advance_unsafe()
                print(f"Autotune: status={self.state['status']} next={self.state['current_batch_size']} "
                      f"best_observed={self.best()}", flush=True)
        self.save()

    def failure(self, size, seconds, reason):
        r = self.record(size)
        r['ooms'] += 1
        r['failed_wall_seconds'] += seconds
        old = self.state['blocked_at']
        self.state['blocked_at'] = size if old is None else min(old, size)
        self.state['last_failure'] = {'timestamp': utc_now(), 'batch_size': size, 'reason': reason}
        if self.state['status'] == 'selected':
            self.state['selected_batch_size'] = self.best()
        else:
            self.state.update(trial_batches=0, trial_tokens=0, partial_batches=0)
        self._advance_unsafe()
        self.save()

    def finish(self):
        if self.state['status'] != 'selected':
            self.state['status'] = 'dataset_finished_before_full_search'
        self.state['selected_batch_size'] = self.best()
        self.state['finished_at'] = utc_now()
        self.save()
