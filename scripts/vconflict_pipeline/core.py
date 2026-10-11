"""Compatibility exports for standalone tools; pipeline modules import their owners."""

from pathlib import Path

from .settings import PROJECT_ROOT
from .common import (
    ID_PATTERN,
    CJK_PATTERN,
    PipelineError,
    utc_now,
    is_english_text,
    normalize_text,
    sha256_text,
    require_nonempty_string,
    validate_id,
    validate_group,
    video_case_context,
    require_question_only_compatible,
)
from .paths import (
    SOURCE_CASE_HEADING,
    grouped_dir,
    resolve_video_path as _resolve_video_path,
    parse_source_case,
    iter_source_paths,
    iter_case_paths,
)
from .storage import (
    atomic_write_text,
    atomic_write_json,
    read_json,
    load_case,
)
from .schema import (
    QUESTION_EVALUATION_LEAK,
    EXPLICIT_PRIOR_CUES,
    JUDGMENT_SCHEMA,
    validate_question,
    validate_questions,
    validate_draft,
    empty_video,
    draft_to_case,
    validate_qa_result,
    validate_case,
)
from .result_rules import (
    qa_result_input_mode,
    canonical_verdict,
    FILTER_RESULT_FIELDS,
    filter_field,
    set_filter_field,
)
from .authoring_definitions import (
    SINGLE_QUESTION_SCHEMA,
    QUESTION_OUTPUT_SCHEMA,
    AUTHOR_OUTPUT_SCHEMA,
    CASE_DRAFT_SCHEMA,
    AUTHOR_VERIFY_SCHEMA,
    QUESTION_VERIFY_SCHEMA,
)

def resolve_video_path(local_path: str, must_exist: bool = False) -> Path:
    """Retain standalone callers' configurable core.PROJECT_ROOT."""
    return _resolve_video_path(local_path, must_exist, project_root=PROJECT_ROOT)


__all__ = [
    'PROJECT_ROOT',
    'ID_PATTERN',
    'CJK_PATTERN',
    'PipelineError',
    'utc_now',
    'is_english_text',
    'normalize_text',
    'sha256_text',
    'require_nonempty_string',
    'validate_id',
    'validate_group',
    'video_case_context',
    'require_question_only_compatible',
    'SOURCE_CASE_HEADING',
    'grouped_dir',
    'resolve_video_path',
    'parse_source_case',
    'iter_source_paths',
    'iter_case_paths',
    'atomic_write_text',
    'atomic_write_json',
    'read_json',
    'load_case',
    'QUESTION_EVALUATION_LEAK',
    'EXPLICIT_PRIOR_CUES',
    'JUDGMENT_SCHEMA',
    'validate_question',
    'validate_questions',
    'validate_draft',
    'empty_video',
    'draft_to_case',
    'validate_qa_result',
    'validate_case',
    'qa_result_input_mode',
    'canonical_verdict',
    'FILTER_RESULT_FIELDS',
    'filter_field',
    'set_filter_field',
    'SINGLE_QUESTION_SCHEMA',
    'QUESTION_OUTPUT_SCHEMA',
    'AUTHOR_OUTPUT_SCHEMA',
    'CASE_DRAFT_SCHEMA',
    'AUTHOR_VERIFY_SCHEMA',
    'QUESTION_VERIFY_SCHEMA',
]
