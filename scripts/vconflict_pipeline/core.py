"""Schema-4 case validation, discovery, and atomic storage."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .settings import *

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
QUESTION_EVALUATION_LEAK = re.compile(r"\b(conflict|incorrect)\b", re.IGNORECASE)
EXPLICIT_PRIOR_CUES = re.compile(
    r"\b(normally|usually|typically|should)\b|\bexpected to\b|\bsupposed to\b",
    re.IGNORECASE,
)
SOURCE_CASE_HEADING = re.compile(
    r"^###\s+(?:(?P<legacy_number>\d+(?:\.\d+)*)\s+)?(?P<title>.+?)\s*$"
)


class PipelineError(Exception):
    """An expected, user-facing pipeline error."""

SINGLE_QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "question_en": {"type": "string"},
        "conflict_video_reference_en": {"type": "string"},
        "normal_control_reference_en": {"type": "string"},
    },
    "required": [
        "question_en",
        "conflict_video_reference_en",
        "normal_control_reference_en",
    ],
}

QUESTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 1,
            "maxItems": QUESTION_LIMIT,
            "items": SINGLE_QUESTION_SCHEMA,
        }
    },
    "required": ["questions"],
}

AUTHOR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "conflict_spec": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "normal_fact_en": {"type": "string"},
                "intended_video_fact_en": {"type": "string"},
            },
            "required": ["normal_fact_en", "intended_video_fact_en"],
        },
        "conflict_video_prompts_en": {
            "type": "array",
            "minItems": 1,
            "maxItems": CONFLICT_VIDEO_LIMIT,
            "items": {"type": "string"},
        },
        "control_video_prompt_en": {"type": "string"},
    },
    "required": [
        "conflict_spec",
        "conflict_video_prompts_en",
        "control_video_prompt_en",
    ],
}

CASE_DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "case_id": {"type": "string"},
        "title": {"type": "string"},
        **AUTHOR_OUTPUT_SCHEMA["properties"],
    },
    "required": [
        "case_id",
        "title",
        *AUTHOR_OUTPUT_SCHEMA["required"],
    ],
}

AUTHOR_VERIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "valid": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "case": CASE_DRAFT_SCHEMA,
    },
    "required": ["valid", "issues", "case"],
}

QUESTION_VERIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "valid": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "questions": {
            "type": "array",
            "minItems": 1,
            "maxItems": QUESTION_LIMIT,
            "items": SINGLE_QUESTION_SCHEMA,
        },
    },
    "required": ["valid", "issues", "questions"],
}

JUDGMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "extracted_answer": {"type": "string"},
        "verdict": {"type": "string", "enum": sorted(VERDICTS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "string"},
    },
    "required": ["extracted_answer", "verdict", "confidence", "evidence"],
}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def is_english_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and bool(re.search(r"[A-Za-z]", value))
        and not CJK_PATTERN.search(value)
    )


def normalize_text(value: str) -> str:
    return re.sub(r"\W+", " ", value.lower()).strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def qa_result_input_mode(result: dict[str, Any]) -> str:
    """Treat pre-description results as video results."""
    value = result.get("input_mode", "video")
    return value if isinstance(value, str) else ""


def canonical_verdict(value: str) -> str:
    """Map persisted legacy labels to the current reporting vocabulary."""
    return "context_grounded" if value == "video_grounded" else value


def require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"{field} must be a non-empty string.")
    return value.strip()


def validate_id(value: Any, field: str) -> str:
    result = require_nonempty_string(value, field)
    if not ID_PATTERN.fullmatch(result):
        raise PipelineError(
            f"{field} must use lowercase letters, numbers, underscores, or hyphens."
        )
    return result


def validate_group(value: Any) -> str:
    return validate_id(value, "group")


def grouped_dir(root: Path, group: str | None) -> Path:
    return root if group is None else root / validate_group(group)


def resolve_video_path(local_path: str, must_exist: bool = False) -> Path:
    supplied = Path(local_path)
    if supplied.is_absolute():
        raise PipelineError("Video local_path must be relative to the project root.")
    candidate = (PROJECT_ROOT / supplied).resolve(strict=False)
    video_root = (PROJECT_ROOT / "videos" / "seedance").resolve(strict=False)
    if not _is_within(candidate, video_root):
        raise PipelineError("Video local_path must stay within videos/seedance.")
    if candidate.suffix.lower() not in VIDEO_EXTENSIONS:
        raise PipelineError(f"Unsupported video extension in local_path: {local_path}")
    if must_exist and (not candidate.exists() or not candidate.is_file()):
        raise PipelineError(f"Video file was not found: {local_path}")
    return candidate


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as exc:
        raise PipelineError(f"Could not write {path}: {exc}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PipelineError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Expected a JSON object in {path}.")
    return value


def parse_source_case(path: Path) -> dict[str, str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"Could not read source case {path}: {exc}") from exc
    first_line = content.splitlines()[0] if content.splitlines() else ""
    heading = SOURCE_CASE_HEADING.match(first_line)
    if not heading:
        raise PipelineError(f"Source case must start with a level-three heading: {path}")
    title = heading.group("title").strip()
    case_id = validate_id(path.stem, "source filename")
    return {
        "case_id": case_id,
        "title": title,
        "content": content,
    }


def iter_source_paths(
    source_dir: Path,
    case_ids: Iterable[str] | None = None,
) -> list[Path]:
    selected = set(case_ids or [])
    if not source_dir.exists():
        raise PipelineError(f"Source case directory was not found: {source_dir}")
    paths = sorted(source_dir.glob("*.md"))
    if selected:
        paths = [path for path in paths if path.stem in selected]
        missing = selected - {path.stem for path in paths}
        if missing:
            raise PipelineError(f"Source cases were not found: {', '.join(sorted(missing))}")
    if not paths:
        raise PipelineError(f"No source case Markdown files were found in {source_dir}.")
    return paths


def iter_case_paths(
    dataset_dir: Path,
    case_ids: Iterable[str] | None = None,
) -> list[Path]:
    selected = set(case_ids or [])
    if not dataset_dir.exists():
        raise PipelineError(f"Dataset directory was not found: {dataset_dir}")
    paths = sorted(dataset_dir.glob("*.json"))
    if selected:
        paths = [path for path in paths if path.stem in selected]
        missing = selected - {path.stem for path in paths}
        if missing:
            raise PipelineError(f"Case files were not found: {', '.join(sorted(missing))}")
    if not paths:
        raise PipelineError(f"No case JSON files were found in {dataset_dir}.")
    return paths


def validate_question(
    question: Any,
    prefix: str,
) -> None:
    if not isinstance(question, dict):
        raise PipelineError(f"{prefix} must be an object.")
    question_id = validate_id(question.get("question_id"), f"{prefix}.question_id")
    values = {
        "text_en": question.get("text_en"),
        "conflict_video_reference_en": question.get("conflict_video_reference_en"),
        "normal_control_reference_en": question.get("normal_control_reference_en"),
    }
    for field, raw in values.items():
        value = require_nonempty_string(raw, f"{prefix}.{field}")
        if not is_english_text(value):
            raise PipelineError(f"{prefix}.{field} must be English.")
    question_text = str(values["text_en"])
    if QUESTION_EVALUATION_LEAK.search(question_text):
        raise PipelineError(f"{prefix}.text_en leaks the conflict evaluation.")
    if normalize_text(str(values["conflict_video_reference_en"])) == normalize_text(
        str(values["normal_control_reference_en"])
    ):
        raise PipelineError(f"{prefix} reference answers must be different.")

    has_prior_cue = EXPLICIT_PRIOR_CUES.search(question_text) is not None
    if re.fullmatch(r"q\d{3}", question_id):
        if "question_pair_id" in question or "question_type" in question:
            raise PipelineError(
                f"{prefix} must not contain question_pair_id or question_type."
            )
        if has_prior_cue:
            raise PipelineError(
                f"{prefix}.text_en must not contain an explicit prior cue."
            )
        return

    legacy_match = re.fullmatch(r"(q\d{3})_(implicit|explicit)", question_id)
    if legacy_match is None:
        raise PipelineError(f"{prefix}.question_id must use the form q001.")
    pair_id = validate_id(
        question.get("question_pair_id"), f"{prefix}.question_pair_id"
    )
    question_type = question.get("question_type")
    expected_type = (
        "implicit_prior" if legacy_match.group(2) == "implicit" else "explicit_prior"
    )
    if pair_id != legacy_match.group(1) or question_type != expected_type:
        raise PipelineError(
            f"{prefix} has inconsistent legacy question identity fields."
        )
    if question_type == "implicit_prior" and has_prior_cue:
        raise PipelineError(f"{prefix}.text_en must not contain an explicit prior cue.")
    if question_type == "explicit_prior" and not has_prior_cue:
        raise PipelineError(f"{prefix}.text_en must contain an explicit prior cue.")


def validate_questions(
    questions_raw: Any,
) -> dict[str, dict[str, Any]]:
    if not isinstance(questions_raw, list):
        raise PipelineError("questions must be an array.")
    legacy_limit = QUESTION_LIMIT * 2
    if questions_raw and not 1 <= len(questions_raw) <= legacy_limit:
        raise PipelineError(
            f"questions must be empty or contain 1-{legacy_limit} entries."
        )

    questions: dict[str, dict[str, Any]] = {}
    normalized_questions: set[str] = set()
    for index, question in enumerate(questions_raw):
        prefix = f"questions[{index}]"
        validate_question(question, prefix)
        question_id = question["question_id"]
        if question_id in questions:
            raise PipelineError(f"Duplicate question_id: {question_id}")
        questions[question_id] = question
        normalized = normalize_text(question["text_en"])
        if normalized in normalized_questions:
            raise PipelineError("Duplicate questions are not allowed.")
        normalized_questions.add(normalized)

    if not questions_raw:
        return questions

    simple_ids = {
        question_id
        for question_id in questions
        if re.fullmatch(r"q\d{3}", question_id)
    }
    if simple_ids:
        if len(simple_ids) != len(questions):
            raise PipelineError("New and legacy question formats must not be mixed.")
        if len(questions) > QUESTION_LIMIT:
            raise PipelineError(
                f"questions must contain at most {QUESTION_LIMIT} entries."
            )
        expected_ids = {
            f"q{index:03d}" for index in range(1, len(questions) + 1)
        }
        if simple_ids != expected_ids:
            raise PipelineError(
                "Question IDs must be contiguous and start at q001."
            )
        return questions

    pairs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for question in questions.values():
        pair_id = question["question_pair_id"]
        question_type = question["question_type"]
        if question_type in pairs[pair_id]:
            raise PipelineError(
                f"Question pair {pair_id} contains duplicate {question_type} entries."
            )
        pairs[pair_id][question_type] = question
    expected_pair_ids = {f"q{index:03d}" for index in range(1, len(pairs) + 1)}
    if set(pairs) != expected_pair_ids or len(pairs) > QUESTION_LIMIT:
        raise PipelineError("Legacy question pairs must be contiguous from q001.")
    allowed_shapes = (
        frozenset({"implicit_prior"}),
        frozenset({"implicit_prior", "explicit_prior"}),
    )
    member_shapes = {frozenset(members) for members in pairs.values()}
    if len(member_shapes) != 1 or next(iter(member_shapes)) not in allowed_shapes:
        raise PipelineError("Legacy question pairs have inconsistent members.")
    if member_shapes == {allowed_shapes[1]}:
        for pair_id, members in pairs.items():
            for reference_field in (
                "conflict_video_reference_en",
                "normal_control_reference_en",
            ):
                if members["implicit_prior"][reference_field] != members[
                    "explicit_prior"
                ][reference_field]:
                    raise PipelineError(
                        f"Question pair {pair_id} must share {reference_field}."
                    )
    return questions


def validate_draft(draft: Any) -> None:
    if not isinstance(draft, dict):
        raise PipelineError("Draft case must be an object.")
    validate_id(draft.get("case_id"), "case_id")
    title = require_nonempty_string(draft.get("title"), "title")
    if not is_english_text(title):
        raise PipelineError("title must be English.")
    conflict = draft.get("conflict_spec")
    if not isinstance(conflict, dict):
        raise PipelineError("conflict_spec must be an object.")
    normal = require_nonempty_string(
        conflict.get("normal_fact_en"), "conflict_spec.normal_fact_en"
    )
    intended = require_nonempty_string(
        conflict.get("intended_video_fact_en"),
        "conflict_spec.intended_video_fact_en",
    )
    if not is_english_text(normal) or not is_english_text(intended):
        raise PipelineError("conflict_spec facts must be English.")
    if normalize_text(normal) == normalize_text(intended):
        raise PipelineError("Normal and intended video facts must be different.")

    prompts = draft.get("conflict_video_prompts_en")
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= CONFLICT_VIDEO_LIMIT:
        raise PipelineError(
            f"conflict_video_prompts_en must contain 1-{CONFLICT_VIDEO_LIMIT} entries."
        )
    normalized_prompts: set[str] = set()
    for index, prompt in enumerate(prompts):
        prompt = require_nonempty_string(
            prompt, f"conflict_video_prompts_en[{index}]"
        )
        if not is_english_text(prompt):
            raise PipelineError(
                f"conflict_video_prompts_en[{index}] must be English."
            )
        normalized = normalize_text(prompt)
        if normalized in normalized_prompts:
            raise PipelineError("Duplicate conflict prompts are not allowed.")
        normalized_prompts.add(normalized)
    control = require_nonempty_string(
        draft.get("control_video_prompt_en"), "control_video_prompt_en"
    )
    if not is_english_text(control):
        raise PipelineError("control_video_prompt_en must be English.")
    if normalize_text(control) in normalized_prompts:
        raise PipelineError("Control prompt must differ from every conflict prompt.")


def empty_video(
    *,
    case_id: str,
    video_id: str,
    role: str,
    prompt: str,
    group: str | None = None,
) -> dict[str, Any]:
    video_dir = Path("videos") / "seedance"
    if group is not None:
        video_dir /= validate_group(group)
    video_dir /= case_id
    return {
        "video_id": video_id,
        "role": role,
        "seedance_prompt_en": prompt.strip(),
        "task_id": None,
        "status": "pending",
        "local_path": (video_dir / f"{video_id}.mp4").as_posix(),
        "human_review": "pending",
        "qa_results": [],
    }


def draft_to_case(
    draft: dict[str, Any],
    *,
    group: str | None = None,
) -> dict[str, Any]:
    validate_draft(draft)
    case_id = draft["case_id"]
    videos = [
        empty_video(
            case_id=case_id,
            video_id=f"v{index:03d}",
            role="conflict",
            prompt=prompt,
            group=group,
        )
        for index, prompt in enumerate(
            draft["conflict_video_prompts_en"],
            start=1,
        )
    ]
    videos.append(
        empty_video(
            case_id=case_id,
            video_id="control",
            role="control",
            prompt=draft["control_video_prompt_en"],
            group=group,
        )
    )
    case = {
        "schema_version": CASE_SCHEMA_VERSION,
        "case_id": case_id,
        "title": draft["title"].strip(),
        "conflict_spec": {
            "normal_fact_en": draft["conflict_spec"]["normal_fact_en"].strip(),
            "intended_video_fact_en": draft["conflict_spec"][
                "intended_video_fact_en"
            ].strip(),
        },
        "questions": [],
        "videos": videos,
    }
    validate_case(case)
    return case


def validate_qa_result(result: Any, prefix: str, questions: dict[str, dict[str, Any]]) -> None:
    if not isinstance(result, dict):
        raise PipelineError(f"{prefix} must be an object.")
    validate_id(result.get("run_id"), f"{prefix}.run_id")
    question_id = validate_id(result.get("question_id"), f"{prefix}.question_id")
    if question_id not in questions:
        raise PipelineError(f"{prefix} references unknown question_id: {question_id}")
    if result.get("question") != questions[question_id]["text_en"]:
        raise PipelineError(f"{prefix}.question does not match the case question.")
    require_nonempty_string(result.get("raw_answer"), f"{prefix}.raw_answer")
    input_mode = qa_result_input_mode(result)
    if input_mode not in INPUT_MODES:
        raise PipelineError(f"{prefix}.input_mode is invalid.")
    context_sha256 = result.get("context_sha256")
    video_sha256 = result.get("video_sha256")
    if context_sha256 is not None:
        require_nonempty_string(context_sha256, f"{prefix}.context_sha256")
    if video_sha256 is not None:
        require_nonempty_string(video_sha256, f"{prefix}.video_sha256")
    if (
        input_mode == "video"
        and context_sha256 is not None
        and video_sha256 is not None
    ):
        if context_sha256 != video_sha256:
            raise PipelineError(
                f"{prefix}.context_sha256 must match video_sha256 for video input."
            )
    if input_mode == "description":
        context_text = require_nonempty_string(
            result.get("context_text_en"), f"{prefix}.context_text_en"
        )
        if (
            context_sha256 is not None
            and sha256_text(context_text) != context_sha256
        ):
            raise PipelineError(
                f"{prefix}.context_sha256 does not match context_text_en."
            )
    require_nonempty_string(result.get("model"), f"{prefix}.model")
    thinking_effort = result.get("thinking_effort")
    if thinking_effort is not None:
        require_nonempty_string(thinking_effort, f"{prefix}.thinking_effort")
    effective_effort = result.get("effective_reasoning_effort")
    if effective_effort is not None:
        require_nonempty_string(
            effective_effort,
            f"{prefix}.effective_reasoning_effort",
        )
    temperature = result.get("temperature")
    if temperature is not None and not isinstance(temperature, (int, float)):
        raise PipelineError(f"{prefix}.temperature must be a number.")
    judgment = result.get("judgment")
    if judgment is None:
        return
    if not isinstance(judgment, dict):
        raise PipelineError(f"{prefix}.judgment must be an object or null.")
    if judgment.get("verdict") not in ACCEPTED_VERDICTS:
        raise PipelineError(f"{prefix}.judgment.verdict is invalid.")
    confidence = judgment.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise PipelineError(f"{prefix}.judgment.confidence is invalid.")
    require_nonempty_string(
        judgment.get("extracted_answer"), f"{prefix}.judgment.extracted_answer"
    )
    require_nonempty_string(judgment.get("evidence"), f"{prefix}.judgment.evidence")


def validate_case(case: Any) -> None:
    if not isinstance(case, dict):
        raise PipelineError("Case must be an object.")
    schema_version = case.get("schema_version")
    if schema_version != CASE_SCHEMA_VERSION:
        raise PipelineError(f"schema_version must be {CASE_SCHEMA_VERSION}.")
    case_id = validate_id(case.get("case_id"), "case_id")
    title = require_nonempty_string(case.get("title"), "title")
    if not is_english_text(title):
        raise PipelineError("title must be English.")
    if "source" in case:
        raise PipelineError("source is not part of the compact schema.")

    conflict = case.get("conflict_spec")
    if not isinstance(conflict, dict):
        raise PipelineError("conflict_spec must be an object.")
    normal = require_nonempty_string(
        conflict.get("normal_fact_en"), "conflict_spec.normal_fact_en"
    )
    intended = require_nonempty_string(
        conflict.get("intended_video_fact_en"),
        "conflict_spec.intended_video_fact_en",
    )
    if not is_english_text(normal) or not is_english_text(intended):
        raise PipelineError("conflict_spec facts must be English.")
    if normalize_text(normal) == normalize_text(intended):
        raise PipelineError("Normal and intended video facts must be different.")

    questions = validate_questions(case.get("questions"))

    videos = case.get("videos")
    if not isinstance(videos, list) or not 2 <= len(videos) <= TOTAL_VIDEO_LIMIT:
        raise PipelineError(f"videos must contain 2-{TOTAL_VIDEO_LIMIT} entries.")
    roles = Counter(video.get("role") for video in videos if isinstance(video, dict))
    if roles["control"] != 1:
        raise PipelineError("Each case must contain exactly one control video.")
    if not 1 <= roles["conflict"] <= CONFLICT_VIDEO_LIMIT:
        raise PipelineError(
            f"Each case must contain 1-{CONFLICT_VIDEO_LIMIT} conflict videos."
        )
    if set(roles) - VIDEO_ROLES:
        raise PipelineError("Video role must be conflict or control.")

    video_ids: set[str] = set()
    local_paths: set[str] = set()
    prompts: set[str] = set()
    for index, video in enumerate(videos):
        prefix = f"videos[{index}]"
        if not isinstance(video, dict):
            raise PipelineError(f"{prefix} must be an object.")
        video_id = validate_id(video.get("video_id"), f"{prefix}.video_id")
        if video_id in video_ids:
            raise PipelineError(f"Duplicate video_id: {video_id}")
        video_ids.add(video_id)
        if video.get("role") not in VIDEO_ROLES:
            raise PipelineError(f"{prefix}.role is invalid.")
        prompt = require_nonempty_string(
            video.get("seedance_prompt_en"), f"{prefix}.seedance_prompt_en"
        )
        if not is_english_text(prompt):
            raise PipelineError(f"{prefix}.seedance_prompt_en must be English.")
        normalized_prompt = normalize_text(prompt)
        if normalized_prompt in prompts:
            raise PipelineError("Duplicate Seedance prompts are not allowed.")
        prompts.add(normalized_prompt)
        description = video.get("description")
        if description is not None:
            if video.get("role") != "conflict":
                raise PipelineError(f"{prefix}.description is only valid for conflict videos.")
            if not isinstance(description, dict):
                raise PipelineError(f"{prefix}.description must be an object or null.")
            context_en = require_nonempty_string(
                description.get("context_en"), f"{prefix}.description.context_en"
            )
            if not is_english_text(context_en):
                raise PipelineError(f"{prefix}.description.context_en must be English.")
            context_prefix = description.get("context_prefix_en")
            if context_prefix is not None:
                context_prefix = require_nonempty_string(
                    context_prefix, f"{prefix}.description.context_prefix_en"
                )
                if not is_english_text(context_prefix):
                    raise PipelineError(
                        f"{prefix}.description.context_prefix_en must be English."
                    )
                if not context_en.startswith(context_prefix):
                    raise PipelineError(
                        f"{prefix}.description.context_en must start with its prefix."
                    )
            if description.get("source") != "seedance_prompt_en":
                raise PipelineError(
                    f"{prefix}.description.source must be seedance_prompt_en."
                )
            source_sha256 = require_nonempty_string(
                description.get("source_sha256"),
                f"{prefix}.description.source_sha256",
            )
            if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
                raise PipelineError(
                    f"{prefix}.description.source_sha256 must be a SHA-256 hex digest."
                )
            require_nonempty_string(
                description.get("generator_model"),
                f"{prefix}.description.generator_model",
            )
            require_nonempty_string(
                description.get("generated_at"),
                f"{prefix}.description.generated_at",
            )
            for request_field in ("generator_request_id", "validator_request_id"):
                request_id = description.get(request_field)
                if request_id is not None and not isinstance(request_id, str):
                    raise PipelineError(
                        f"{prefix}.description.{request_field} must be a string or null."
                    )
        if video.get("status") not in VIDEO_STATUSES:
            raise PipelineError(f"{prefix}.status is invalid.")
        if video.get("human_review") not in REVIEW_STATUSES:
            raise PipelineError(f"{prefix}.human_review is invalid.")
        task_id = video.get("task_id")
        if task_id is not None and not isinstance(task_id, str):
            raise PipelineError(f"{prefix}.task_id must be a string or null.")
        if "url" in video:
            raise PipelineError(f"{prefix}.url is not part of the compact schema.")
        local_path = require_nonempty_string(
            video.get("local_path"), f"{prefix}.local_path"
        )
        resolve_video_path(local_path)
        if local_path in local_paths:
            raise PipelineError(f"Duplicate local_path: {local_path}")
        local_paths.add(local_path)
        local_parts = Path(local_path).as_posix().split("/")
        if (
            len(local_parts) not in (4, 5)
            or local_parts[:2] != ["videos", "seedance"]
            or local_parts[-2] != case_id
        ):
            raise PipelineError(
                f"{prefix}.local_path must use videos/seedance/<case_id>/ "
                "or videos/seedance/<group>/<case_id>/."
            )
        if len(local_parts) == 5:
            validate_group(local_parts[2])
        qa_results = video.get("qa_results")
        if not isinstance(qa_results, list):
            raise PipelineError(f"{prefix}.qa_results must be an array.")
        for result_index, result in enumerate(qa_results):
            validate_qa_result(
                result,
                f"{prefix}.qa_results[{result_index}]",
                questions,
            )
            if (
                video["role"] == "control"
                and qa_result_input_mode(result) == "description"
            ):
                raise PipelineError(
                    f"{prefix}.qa_results[{result_index}] uses description input "
                    "for a control video."
                )


def load_case(path: Path) -> dict[str, Any]:
    case = read_json(path)
    try:
        validate_case(case)
    except PipelineError as exc:
        raise PipelineError(f"{path}: {exc}") from exc
    if path.stem != case["case_id"]:
        raise PipelineError(
            f"{path}: filename must match case_id ({case['case_id']}.json)."
        )
    return case
