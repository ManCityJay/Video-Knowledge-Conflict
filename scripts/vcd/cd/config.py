"""Internal worker configuration shared by both public launchers."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

from vconflict_pipeline.settings import DEFAULT_CASE_DIR, PROJECT_ROOT

FAMILIES = ('qwen', 'cosmos', 'gemma')


@dataclass
class WorkerConfig:
    model_family: str
    output: Path = PROJECT_ROOT / 'results/vcd'
    dataset_dir: Path = DEFAULT_CASE_DIR
    model_path: str | None = None
    group: list[str] | None = None
    case_id: list[str] | None = None
    video_id: list[str] | None = None
    question_id: list[str] | None = None
    alpha: float = 1.0
    beta: float = .1
    max_new_tokens: int = 8192
    thinking_token_budget: int | None = 6144
    disable_thinking: bool = False
    dtype: str = 'bfloat16'
    based: bool = False
    question_no_based: bool = False
    force_qa: bool = False
    force_judge: bool = False
    summarize_only: bool = False
    qa_only: bool = False
    max_token_log: Path | None = None
    judge_concurrency: int = 24
    judge_rpm: float = 20
    openrouter_concurrency: int = 24
    openrouter_rpm: float = 20
    timeout: int = 600
    max_retries: int = 4
    run_id: str | None = None

    @property
    def device(self):
        return 'cuda:0'

    @property
    def thinking_effort(self):
        return None if self.disable_thinking else 'default'

    def __post_init__(self):
        if self.disable_thinking:
            self.thinking_token_budget = None


def from_arguments(args, family):
    values = {field.name: getattr(args, field.name) for field in fields(WorkerConfig)
              if hasattr(args, field.name) and field.name != 'model_family'}
    values['output'] = args.output / family
    return WorkerConfig(model_family=family, **values)
