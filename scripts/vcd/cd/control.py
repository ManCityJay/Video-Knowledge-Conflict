"""Token-sequence reasoning boundaries and budget control for all three models."""
from __future__ import annotations

BOUNDARIES = {
    "cosmos": ("<think>", "</think>"),
    "qwen": ("<think>", "</think>"),
    "gemma": ("<|channel>thought\n", "<channel|>"),
}


def last_sequence(ids, sequence):
    for index in range(len(ids) - len(sequence), -1, -1):
        if ids[index:index + len(sequence)] == sequence:
            return index
    return -1


class ReasoningControl:
    """Count only an open reasoning span; force every token of its closing marker."""

    def __init__(self, tokenizer, prompt_ids, *, family, budget):
        start, end = BOUNDARIES[family]
        self.start = tokenizer.encode(start, add_special_tokens=False)
        self.end = tokenizer.encode(end, add_special_tokens=False)
        if not self.start or not self.end:
            raise ValueError("Tokenizer cannot encode reasoning boundaries")
        self.prompt_length = len(prompt_ids)
        opening = last_sequence(prompt_ids, self.start)
        closing = last_sequence(prompt_ids, self.end)
        self.in_think = opening > closing
        self.think_count = len(prompt_ids) - opening - len(self.start) if self.in_think else 0
        self.budget = budget
        self.seen = 0
        self.tail = []
        self.queue = []

    def __call__(self, input_ids, scores):
        if input_ids.shape[0] != 1:
            raise ValueError("Reasoning control requires batch size one")
        new = input_ids[0, self.prompt_length + self.seen:].tolist()
        self.seen += len(new)
        for token in new:
            self.tail.append(token)
            self.tail = self.tail[-max(len(self.start), len(self.end)):]
            if self.in_think:
                self.think_count += 1
            if self.tail[-len(self.start):] == self.start:
                self.in_think, self.think_count = True, 0
            if self.tail[-len(self.end):] == self.end:
                self.in_think, self.think_count = False, 0
        if self.budget is None:
            return scores
        if not self.queue and self.in_think and self.think_count >= self.budget:
            # If the model already started a multi-token end marker, complete it.
            partial = 0
            for size in range(1, len(self.end)):
                if self.tail[-size:] == self.end[:size]:
                    partial = size
            self.queue = self.end[partial:]
        if not self.queue:
            return scores
        token = self.queue.pop(0)
        out = scores.new_full(scores.shape, float("-inf"))
        out[:, token] = 0
        return out

