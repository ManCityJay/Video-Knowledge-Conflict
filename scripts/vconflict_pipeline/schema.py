"""Schema-4 validation and construction of case records."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .common import (
    PipelineError,
    is_english_text,
    normalize_text,
    require_nonempty_string,
    sha256_text,
    validate_group,
    validate_id,
)
from .paths import resolve_video_path
from .result_rules import FILTER_RESULT_FIELDS, filter_field, qa_result_input_mode
from .settings import (
    ACCEPTED_VERDICTS,
    CASE_SCHEMA_VERSION,
    CONFLICT_VIDEO_LIMIT,
    INPUT_MODES,
    QUESTION_LIMIT,
    VERDICTS,
    VIDEO_ROLES,
    VIDEO_STATUSES,
)


QUESTION_EVALUATION_LEAK = re.compile(r"\b(conflict|incorrect)\b", re.IGNORECASE)


EXPLICIT_PRIOR_CUES = re.compile(
    r"\b(normally|usually|typically|should)\b|\bexpected to\b|\bsupposed to\b",
    re.IGNORECASE,
)


JUDGMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": sorted(VERDICTS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["verdict", "confidence"],
}


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
    *,
    allow_question_only_results: bool = False,
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

    for index, question in enumerate(questions_raw):
        for field in FILTER_RESULT_FIELDS:
            filter_results = question.get(field, [])
            filter_prefix = f"questions[{index}].{field}"
            if not isinstance(filter_results, list):
                raise PipelineError(f"{filter_prefix} must be an array.")
            for result_index, result in enumerate(filter_results):
                result_prefix = f"{filter_prefix}[{result_index}]"
                validate_qa_result(result, result_prefix, questions)
                if result.get("question_id") != question["question_id"]:
                    raise PipelineError(f"{result_prefix} must reference its owning question.")
                stage = filter_field(result, "stage")
                # Retain retired stages only for loading historical filter/baseline records.
                expected_mode = {"question_only": "question_only", "control_video": "video"}.get(stage)
                if expected_mode is None or qa_result_input_mode(result) != expected_mode:
                    raise PipelineError(f"{result_prefix} has an invalid filter stage/input.")
                if not re.fullmatch(r"[0-9a-f]{64}", str(filter_field(result, "fingerprint"))):
                    raise PipelineError(f"{result_prefix} needs a filter SHA-256 fingerprint.")
        results = question.get("question_only_results")
        if results is None:
            continue
        prefix = f"questions[{index}].question_only_results"
        if not allow_question_only_results:
            raise PipelineError(
                f"{prefix} is only valid for case-level questions."
            )
        if not isinstance(results, list):
            raise PipelineError(f"{prefix} must be an array.")
        for result_index, result in enumerate(results):
            result_prefix = f"{prefix}[{result_index}]"
            validate_qa_result(result, result_prefix, questions)
            if qa_result_input_mode(result) != "question_only":
                raise PipelineError(
                    f"{result_prefix}.input_mode must be question_only."
                )
            if result.get("question_id") != question["question_id"]:
                raise PipelineError(
                    f"{result_prefix}.question_id must match its owning question."
                )

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
        allowed_ids = {
            f"q{index:03d}" for index in range(1, QUESTION_LIMIT + 1)
        }
        if not simple_ids <= allowed_ids:
            raise PipelineError(
                f"Question IDs must be between q001 and q{QUESTION_LIMIT:03d}."
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
    allowed_pair_ids = {
        f"q{index:03d}" for index in range(1, QUESTION_LIMIT + 1)
    }
    if not set(pairs) <= allowed_pair_ids or len(pairs) > QUESTION_LIMIT:
        raise PipelineError(
            f"Legacy question pair IDs must be between q001 and "
            f"q{QUESTION_LIMIT:03d}."
        )
    for pair_id, members in pairs.items():
        if {"implicit_prior", "explicit_prior"} <= set(members):
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
    # Retain historical responses after an input edit. Reuse, judging and
    # reporting perform content freshness checks instead of blocking loading.
    require_nonempty_string(result.get("question"), f"{prefix}.question")
    require_nonempty_string(result.get("raw_answer"), f"{prefix}.raw_answer")
    final_answer = result.get("final_answer")
    if final_answer is not None:
        require_nonempty_string(final_answer, f"{prefix}.final_answer")
    if "final_answer_retry_count" in result:
        count = result["final_answer_retry_count"]
        if type(count) is not int or count != 1:
            raise PipelineError(f"{prefix}.final_answer_retry_count must be 1 when present.")
    input_mode = qa_result_input_mode(result)
    if input_mode not in INPUT_MODES:
        raise PipelineError(f"{prefix}.input_mode is invalid.")
    if "based" in result:
        if input_mode == "question_only":
            raise PipelineError(f"{prefix}.based is not valid for question-only input.")
        if not isinstance(result["based"], bool):
            raise PipelineError(f"{prefix}.based must be a boolean.")
    if input_mode != "video" and "work_title_prefix" in result:
        raise PipelineError(
            f"{prefix}.work_title_prefix is only valid for video input."
        )
    if input_mode == "video" and "work_title_prefix" in result:
        if not isinstance(result["work_title_prefix"], bool):
            raise PipelineError(f"{prefix}.work_title_prefix must be a boolean.")
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
    elif input_mode == "question_only" and "context_text_en" in result:
        raise PipelineError(
            f"{prefix}.context_text_en is not valid for question_only input."
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

    questions = validate_questions(
        case.get("questions"),
        allow_question_only_results=True,
    )

    videos = case.get("videos")
    # Authoring limits apply to one model response, not accumulated reviewed variants.
    curation = case.get("quality_curation")
    if curation is not None and (
        not isinstance(curation, dict)
        or curation.get("reason") != "manual_quality_pruned"
        or not isinstance(curation.get("backup"), str) or not curation["backup"]
    ):
        raise PipelineError("quality_curation must identify the manual curation backup.")
    if not isinstance(videos, list) or not videos:
        raise PipelineError("videos must contain at least one entry.")
    roles = Counter(video.get("role") for video in videos if isinstance(video, dict))
    if roles["control"] > 1:
        raise PipelineError("Each case may contain at most one control video.")
    if not curation and roles["conflict"] < 1:
        raise PipelineError("Each original case must contain at least one conflict video.")
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
        observation = video.get('video_observation')
        if observation is not None:
            if not isinstance(observation, dict):
                raise PipelineError(f'{prefix}.video_observation must be an object or null.')
            if not re.fullmatch(r'[0-9a-f]{64}', str(observation.get('source_sha256', ''))):
                raise PipelineError(f'{prefix}.video_observation requires a video SHA-256.')
            if not is_english_text(observation.get('summary_en')):
                raise PipelineError(f'{prefix}.video_observation.summary_en must be English.')
            if 'context_en' in observation and not is_english_text(observation['context_en']):
                raise PipelineError(f'{prefix}.video_observation.context_en must be English.')
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
            if description.get("source") not in {"seedance_prompt_en", "video"}:
                raise PipelineError(
                    f"{prefix}.description.source must be seedance_prompt_en or video."
                )
            if description.get('source') == 'video' and (
                observation is None or description.get('source_sha256') != observation.get('source_sha256')
            ):
                raise PipelineError(f'{prefix}.description must match its reviewed video observation.')
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
            len(local_parts) not in (4, 5, 6)
            or local_parts[:2] != ["videos", "seedance"]
            or local_parts[-2] != case_id
        ):
            raise PipelineError(
                f"{prefix}.local_path must use videos/seedance/<case_id>/ "
                "videos/seedance/<group>/<case_id>/, or "
                "videos/seedance/<group>/<qualified|unqualified>/<case_id>/."
            )
        if len(local_parts) in (5, 6):
            validate_group(local_parts[2])
        if len(local_parts) == 6 and local_parts[2] == "mathematics_algorithm_conflicts":
            raise PipelineError(f"{prefix}.local_path must use the flat group/case layout; Math review buckets were retired.")
        if len(local_parts) == 6 and local_parts[3] not in {
            "qualified",
            "unqualified",
        }:
            raise PipelineError(
                f"{prefix}.local_path review bucket must be qualified or unqualified."
            )
        context = video.get("variant_context")
        video_questions = questions
        if context is not None:
            if not isinstance(context, dict):
                raise PipelineError(f"{prefix}.variant_context must be an object.")
            video_questions = validate_questions(context.get("questions"))
            facts = context.get("conflict_spec")
            if not isinstance(facts, dict):
                raise PipelineError(f"{prefix}.variant_context.conflict_spec must be an object.")
            for field in ("normal_fact_en", "intended_video_fact_en"):
                value = require_nonempty_string(facts.get(field), f"{prefix}.variant_context.{field}")
                if not is_english_text(value):
                    raise PipelineError(f"{prefix}.variant_context.{field} must be English.")
            if normalize_text(facts["normal_fact_en"]) == normalize_text(facts["intended_video_fact_en"]):
                raise PipelineError(f"{prefix}.variant_context facts must differ.")
        if "question_ids" in video:
            retained = video["question_ids"]
            available = set(video_questions)
            if (not curation or not isinstance(retained, list)
                or any(not isinstance(qid, str) for qid in retained)
                or len(set(retained)) != len(retained)
                or not set(retained) <= available):
                raise PipelineError(f"{prefix}.question_ids must be unique retained question IDs.")
            video_questions = {qid: q for qid, q in video_questions.items() if qid in retained}
        qa_results = video.get("qa_results")
        if not isinstance(qa_results, list):
            raise PipelineError(f"{prefix}.qa_results must be an array.")
        for result_index, result in enumerate(qa_results):
            validate_qa_result(
                result,
                f"{prefix}.qa_results[{result_index}]",
                video_questions,
            )
            if qa_result_input_mode(result) == "question_only":
                raise PipelineError(
                    f"{prefix}.qa_results[{result_index}] must be stored under "
                    "its case-level question."
                )
            if (
                video["role"] == "control"
                and qa_result_input_mode(result) == "description"
            ):
                raise PipelineError(
                    f"{prefix}.qa_results[{result_index}] uses description input "
                    "for a control video."
                )
