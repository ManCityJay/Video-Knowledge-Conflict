"""Thread-safe QA output counts for one command invocation."""

from __future__ import annotations

import threading
from typing import Literal

QADiagnosticStage = Literal["main", "question_only filter", "control filter"]
QADiagnosticReason = Literal["max_tokens_truncated", "missing_final_answer"]
DIAGNOSTIC_STAGES: tuple[QADiagnosticStage, ...] = (
    "main", "question_only filter", "control filter",
)


class QADiagnostics:
    def __init__(self, *, include_truncation: bool) -> None:
        self.include_truncation = include_truncation
        self._lock = threading.Lock()
        self._counts = {
            stage: {"max_tokens_truncated": 0, "missing_final_answer": 0}
            for stage in DIAGNOSTIC_STAGES
        }

    def record(self, stage: QADiagnosticStage, reason: QADiagnosticReason) -> None:
        with self._lock:
            self._counts[stage][reason] += 1

    def print_summary(self) -> None:
        with self._lock:
            snapshot = {stage: counts.copy() for stage, counts in self._counts.items()}
        for stage, counts in snapshot.items():
            fields = []
            if self.include_truncation:
                fields.append(f"max_tokens_truncated={counts['max_tokens_truncated']}")
            fields.append(f"missing_final_answer={counts['missing_final_answer']}")
            print(f"QA output diagnostics ({stage}, this run): " + ", ".join(fields))
