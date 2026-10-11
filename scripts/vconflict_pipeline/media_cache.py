"""Bounded idle media LRU with shared preparation and in-flight pins."""
from __future__ import annotations

from collections import Counter, OrderedDict

from .qa import prepare_video_input


class MediaCache:
    def __init__(self, model, tasks, *, budget=512 * 1024 * 1024):
        self.model, self.tasks = model, tasks
        self.preparing = {}
        self.media = OrderedDict()
        self.media_active = Counter()
        self.media_budget = budget

    def encode(self, task):
        return prepare_video_input(self.model, task.video_path)

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
        self.trim()
        return True

    def trim(self):
        pinned = {key for key, count in self.media_active.items() if count}
        pinned.update(t.media_key for t in self.tasks.values() if t.prepared is not None)
        idle_bytes = sum(len(value) for key, value in self.media.items() if key not in pinned)
        for key in list(self.media):
            if key in pinned:
                continue
            size = len(self.media[key])
            if idle_bytes > self.media_budget or size > self.media_budget:
                del self.media[key]
                idle_bytes -= size

    def release(self, task):
        if task.media_key:
            self.media_active[task.media_key] -= 1
            if self.media_active[task.media_key] <= 0:
                del self.media_active[task.media_key]
            self.trim()

    def pin(self, task):
        if task.media_key:
            self.media_active[task.media_key] += 1

    def clear_preparing(self):
        self.preparing.clear()
