"""Case authoring and question generation."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .authoring_definitions import (
    AUTHOR_OUTPUT_SCHEMA,
    AUTHOR_VERIFY_SCHEMA,
    MATHEMATICS_ALGORITHM_GROUP,
    MATH_QUESTION_ONLY_PROMPT,
    MATH_QUESTION_ONLY_SCHEMA,
    QUESTION_OUTPUT_SCHEMA,
    QUESTION_VERIFY_SCHEMA,
    author_prompts_for_group,
    question_prompts_for_group,
)
from .common import PipelineError, require_nonempty_string, utc_now, video_case_context
from .evidence import observed_summary, qualified_references
from .integrity import question_scope_fingerprint, require_writable_case
from .paths import grouped_dir, iter_case_paths, iter_source_paths, parse_source_case
from .schema import draft_to_case, validate_case, validate_draft, validate_questions
from .settings import AUTHOR_JUDGE_MODEL, CASE_SCHEMA_VERSION, PROJECT_ROOT, QUESTION_LIMIT
from .storage import atomic_write_json, load_case
from .transport import (
    RequestLimiter,
    make_openrouter_limiter,
    openrouter_json,
    require_openrouter_api_key,
)


def verify_draft(
    draft: dict[str, Any],
    *,
    system_prompt: str,
    api_key: str,
    timeout: int,
    max_repairs: int,
    max_retries: int,
    request_limiter: RequestLimiter,
    reference_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current = draft
    locked = {
        "case_id": draft["case_id"],
        "title": draft["title"],
    }
    issues: list[str] = []
    for attempt in range(max_repairs + 1):
        result, _ = openrouter_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "case": current,
                            "previous_issues": issues,
                            "repair_attempt": attempt,
                            "qualified_reference_designs": reference_context or [],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            model=AUTHOR_JUDGE_MODEL,
            schema_name="knowledge_conflict_case_validation",
            schema=AUTHOR_VERIFY_SCHEMA,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            request_limiter=request_limiter,
        )
        candidate = result.get("case")
        if not isinstance(candidate, dict):
            raise PipelineError("Luna Pro validator did not return a case object.")
        candidate.update(locked)
        current = candidate
        issues = [
            item
            for item in result.get("issues", [])
            if isinstance(item, str) and item.strip()
        ]
        local_issue: str | None = None
        try:
            validate_draft(current)
        except PipelineError as exc:
            local_issue = str(exc)
            issues.append(local_issue)
        if result.get("valid") is True and local_issue is None:
            return current
    detail = "; ".join(issues) or "unspecified validation failure"
    raise PipelineError(
        f"Luna Pro could not produce a valid case after {max_repairs} repairs: {detail}"
    )


def command_author(args: argparse.Namespace) -> int:
    author_prompt, author_verify_prompt = author_prompts_for_group(args.group)
    api_key = require_openrouter_api_key()
    request_limiter = make_openrouter_limiter(args)
    written = 0
    failures = 0
    source_dir = grouped_dir(args.source_dir, args.group)
    output_dir = grouped_dir(args.output_dir, args.group)
    source_paths = iter_source_paths(source_dir, args.case_id)

    def run_case(source_path: Path) -> tuple[str, str]:
        source = parse_source_case(source_path)
        output_path = output_dir / f"{source['case_id']}.json"
        if output_path.exists() and not args.force:
            return "skipped", f"Skipping existing case: {output_path}"
        if output_path.exists():
            existing = load_case(output_path)
            require_writable_case(existing, output_path)
            if args.group == MATHEMATICS_ALGORITHM_GROUP and any(
                v.get("human_review") == "verified" for v in existing["videos"]
            ):
                raise PipelineError("Do not overwrite a reviewed math case with author --force. "
                                    "Author the expansion in a separate --output-dir, then promote its reviewed variants.")
        references = (qualified_references(args.group, source['case_id'])
                      if args.group == MATHEMATICS_ALGORITHM_GROUP else [])
        reference_designs = [{k: v for k, v in ref.items() if k != 'chronological_frames'}
                             for ref in references]
        user_content = [{"type": "text", "text": (
            f"<source_case case_id=\"{source['case_id']}\" title=\"{source['title']}\">\n"
            f"{source['content']}\n</source_case>\n"
            "Same-case qualified references (private design evidence, not on-screen text):\n"
            + json.dumps(reference_designs, ensure_ascii=False))}]
        for ref in references:
            user_content.extend([
                {"type": "text", "text": f"Actual chronological frames: {ref['video_id']}"},
                {"type": "image_url", "image_url": {"url": ref['chronological_frames']}},
            ])
        authored, response = openrouter_json(
            messages=[
                {"role": "system", "content": author_prompt},
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            model=AUTHOR_JUDGE_MODEL,
            schema_name="knowledge_conflict_case_authoring",
            schema=AUTHOR_OUTPUT_SCHEMA,
            api_key=api_key,
            timeout=args.timeout,
            max_retries=args.max_retries,
            request_limiter=request_limiter,
        )
        draft = {
            "case_id": source["case_id"],
            "title": source["title"],
            **authored,
        }
        verified = verify_draft(
            draft,
            system_prompt=author_verify_prompt,
            api_key=api_key,
            timeout=args.timeout,
            max_repairs=args.max_repairs,
            max_retries=args.max_retries,
            request_limiter=request_limiter,
            reference_context=reference_designs,
        )
        case = draft_to_case(verified, group=args.group)
        if references:
            case['qualified_reference_designs'] = reference_designs
            for video in case['videos']:
                if video['role'] == 'conflict':
                    video['qualified_reference'] = reference_designs[0]
                    video['require_video_observation'] = True
        atomic_write_json(output_path, case)
        return "written", (
            f"Wrote case {case['case_id']} from request "
            f"{response.get('id') or '(no request id)'}: {output_path}"
        )

    workers = min(args.case_workers, len(source_paths))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_case, path): path for path in source_paths}
        for future in as_completed(futures):
            source_path = futures[future]
            try:
                outcome, message = future.result()
            except PipelineError as exc:
                failures += 1
                print(f"Error authoring {source_path.stem}: {exc}", file=sys.stderr)
                continue
            written += outcome == "written"
            print(message)
    print(f"Wrote {written} authored case(s).")
    return 1 if failures else 0

def question_case_context(
    case: dict[str, Any], video: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build one question scope without mixing independent video variants."""
    if video is None:
        videos = [v for v in case["videos"] if v.get("variant_context") is None]
        conflict_spec = case["conflict_spec"]
    else:
        videos = [video]
        conflict_spec = video_case_context(case, video)["conflict_spec"]
    scope_title = video_case_context(case, video)["title"] if video is not None else case["title"]
    work_title = scope_title.split(":", 1)[0].strip()
    context = {
        "case_id": case["case_id"],
        "title": scope_title,
        "work_title": work_title,
        "conflict_spec": conflict_spec,
        "videos": [
            {
                "role": video["role"],
                "seedance_prompt_en": video["seedance_prompt_en"],
            }
            for video in videos
        ],
    }
    for source_video, evidence in zip(videos, context['videos']):
        if source_video['role'] == 'conflict':
            observation = observed_summary(source_video)
            if observation is not None:
                evidence.pop('seedance_prompt_en', None)
                evidence['observed_video_content_en'] = observation
                evidence['evidence_source'] = 'reviewed_video_pixels'
    if video is not None:
        context["question_scope"] = video["video_id"]
        # Older expansion jobs stored the matching control in a separate case.
        # Only accept it when both facts and the conflict prompt still match.
        source_name = video["variant_context"].get("source_variant_case_path")
        if source_name:
            source_path = (PROJECT_ROOT / source_name).resolve()
            if source_path.is_relative_to(PROJECT_ROOT.resolve()) and source_path.is_file():
                source = load_case(source_path)
                if (source["case_id"] == case["case_id"]
                        and source["conflict_spec"] == conflict_spec
                        and any(v["role"] == "conflict"
                                and v["seedance_prompt_en"] == video["seedance_prompt_en"]
                                for v in source["videos"])):
                    context["matched_control_prompts"] = [
                        v["seedance_prompt_en"] for v in source["videos"]
                        if v["role"] == "control"
                    ]
    return context


def authored_questions_to_questions(
    authored_questions: Any,
) -> list[dict[str, Any]]:
    if (
        not isinstance(authored_questions, list)
        or not 1 <= len(authored_questions) <= QUESTION_LIMIT
    ):
        raise PipelineError(
            f"questions must contain 1-{QUESTION_LIMIT} entries."
        )
    questions: list[dict[str, Any]] = []
    for index, item in enumerate(authored_questions, start=1):
        prefix = f"questions[{index - 1}]"
        if not isinstance(item, dict):
            raise PipelineError(f"{prefix} must be an object.")
        question_id = f"q{index:03d}"
        question_text = require_nonempty_string(
            item.get("question_en"),
            f"{prefix}.question_en",
        )
        conflict_reference = require_nonempty_string(
            item.get("conflict_video_reference_en"),
            f"{prefix}.conflict_video_reference_en",
        )
        normal_reference = require_nonempty_string(
            item.get("normal_control_reference_en"),
            f"{prefix}.normal_control_reference_en",
        )
        questions.append(
            {
                "question_id": question_id,
                "text_en": question_text,
                "conflict_video_reference_en": conflict_reference,
                "normal_control_reference_en": normal_reference,
            }
        )
    validate_questions(questions)
    return questions


def verify_authored_questions(
    questions: list[dict[str, Any]],
    *,
    case_context: dict[str, Any],
    system_prompt: str,
    api_key: str,
    timeout: int,
    max_repairs: int,
    max_retries: int,
    request_limiter: RequestLimiter,
    require_self_contained: bool = False,
    preserve_count: bool = False,
    audit_only: bool = False,
    audit_receipt: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    current = copy.deepcopy(questions)
    original_count = len(questions)
    issues: list[str] = []
    attempts: list[dict[str, Any]] = []
    request_ids = []

    def success(candidate):
        if audit_receipt is not None:
            audit_receipt.update({"status": "passed", "method": "independent_model",
                "model": AUTHOR_JUDGE_MODEL, "reviewed_at": utc_now(),
                "question_only": require_self_contained,
                "request_ids": request_ids[:], "checks": copy.deepcopy(attempts)})
        return candidate

    def fail(detail: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = PROJECT_ROOT / "artifacts" / "question_validation_failures" / f"{stamp}.json"
        # Only authoring data and model outputs, never keys, headers or env vars.
        diagnostic = {
            "case_context": case_context,
            "initial_questions": questions,
            "last_questions": current,
            "max_repairs": max_repairs,
            "attempts": attempts,
            "failure": detail,
        }
        try:
            atomic_write_json(path, diagnostic)
            location = f" Diagnostic: {path}"
        except OSError as exc:
            location = f" Could not save diagnostic: {exc}"
        raise PipelineError(
            f"Luna Pro could not produce valid questions after {max_repairs} repairs: "
            + detail + location
        )

    def audit_texts(candidate: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
        audit, response = openrouter_json(
            messages=[
                {"role": "system", "content": MATH_QUESTION_ONLY_PROMPT},
                {"role": "user", "content": json.dumps({
                    "questions": [q["question_en"] for q in candidate]
                }, ensure_ascii=False)},
            ],
            model=AUTHOR_JUDGE_MODEL,
            schema_name="math_question_only_audit",
            schema=MATH_QUESTION_ONLY_SCHEMA,
            api_key=api_key, timeout=timeout, max_retries=max_retries,
            request_limiter=request_limiter,
        )
        request_ids.append(response.get("id"))
        checks = audit.get("checks")
        if (not isinstance(checks, list) or len(checks) != len(candidate)
                or any(not isinstance(c, dict) or c.get("index") != i
                       for i, c in enumerate(checks, 1))):
            return audit, ["Malformed question-only audit: missing or reordered checks."]
        problems = []
        for i, check in enumerate(checks, 1):
            prefix = f"Question {i} blind audit: "
            if check.get("self_contained") is not True:
                problems.append(prefix + "not self-contained or not uniquely solvable.")
            reported = check.get("issues")
            if not isinstance(reported, list):
                problems.append(prefix + "malformed issues list.")
            else:
                problems.extend(prefix + str(issue) for issue in reported if issue)
            for field in ("answer_en", "derivation_en"):
                if not isinstance(check.get(field), str) or not check[field].strip():
                    problems.append(prefix + f"missing {field}.")
        return audit, problems

    def context_check(candidate, audit, attempt, *, frozen=False):
        payload = {
            "case_design": case_context,
            "questions": candidate,
            "previous_issues": issues,
            "repair_attempt": attempt,
        }
        if audit is not None:
            payload["question_only_audit"] = audit
        if preserve_count:
            payload["repair_constraints"] = (
                f"Return exactly {original_count} questions in the original order. "
                "Preserve each question's semantic target; expand its own premises "
                "and correct its references. Do not add, remove or reorder questions."
            )
        prompt = system_prompt
        if frozen:
            payload["validation_mode"] = "check_only"
            prompt += (
                "\nThis is the FINAL CHECK-ONLY gate, not a repair request. "
                "Return the supplied questions and both references exactly unchanged. "
                "Use the fresh question_only_audit to check the entire normal reference "
                "and the case design to check the conflict reference. If any defect "
                "remains, set valid=false and report concrete issues; do not edit, "
                "paraphrase, expand, add or remove any question or reference. "
                "Set valid=true only when every check passes with an empty issues list."
            )
        result, response = openrouter_json(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            model=AUTHOR_JUDGE_MODEL,
            schema_name="knowledge_conflict_question_validation",
            schema=QUESTION_VERIFY_SCHEMA,
            api_key=api_key, timeout=timeout, max_retries=max_retries,
            request_limiter=request_limiter,
        )
        request_ids.append(response.get("id"))
        return result

    if audit_only:
        authored_questions_to_questions(current)
        audit, blind_issues = audit_texts(current) if require_self_contained else (None, [])
        result = context_check(current, audit, 0, frozen=True)
        attempts.append({"question_only_audit": audit, "context_validation": result})
        if blind_issues or result.get("valid") is not True or result.get("issues") != [] or result.get("questions") != current:
            fail("Check-only audit failed (requires valid=true, no issues, and unchanged questions/references): " + "; ".join(blind_issues + [str(result.get("issues"))]))
        return success(current)

    for attempt in range(max_repairs + 1):
        record: dict[str, Any] = {"attempt": attempt, "input_questions": copy.deepcopy(current)}
        attempts.append(record)
        local_input_issue = None
        try:
            authored_questions_to_questions(current)
        except PipelineError as exc:
            # Draft-level wording/reference defects are repairable. They must
            # reach the context repairer, while saving still requires all gates.
            local_input_issue = str(exc)
            issues = list(dict.fromkeys([*issues, local_input_issue]))
            record["local_input_issue"] = local_input_issue
        try:
            if local_input_issue is not None:
                audit, blind_issues = None, [local_input_issue]
            else:
                audit, blind_issues = audit_texts(current) if require_self_contained else (None, [])
            record["question_only_audit"] = audit
            record["blind_issues"] = blind_issues
            if any(issue.startswith("Malformed question-only audit") for issue in blind_issues):
                raise PipelineError("; ".join(blind_issues))
            result = context_check(current, audit, attempt)
            record["context_validation"] = result
        except PipelineError as exc:
            fail(str(exc))
        candidate = result.get("questions")
        if not isinstance(candidate, list):
            fail("Luna Pro validator did not return questions.")
        issues = [item for item in result.get("issues", []) if isinstance(item, str) and item.strip()]
        if preserve_count and len(candidate) != original_count:
            issues.append(f"Keep exactly {original_count} questions in the original order.")
            record["outcome_issues"] = issues[:]
            continue
        try:
            authored_questions_to_questions(candidate)
        except PipelineError as exc:
            issues.append(str(exc))
            record["outcome_issues"] = issues[:]
            continue
        unchanged_text = len(candidate) == len(current) and all(
            isinstance(old, dict) and new["question_en"] == old.get("question_en")
            for new, old in zip(candidate, current)
        )
        current = candidate
        context_ok = result.get("valid") is True and not issues and result.get("issues") == []
        if not require_self_contained:
            if context_ok:
                return success(current)
        elif context_ok and unchanged_text and not blind_issues:
            # Reference-only repairs are already checked against this same audit.
            return success(current)
        elif not unchanged_text or audit is None:
            # Even the LAST allowed repair gets a fresh, immutable verification.
            # This adds verification calls, never an unbounded extra repair loop.
            try:
                fresh_audit, fresh_issues = audit_texts(current)
                record["final_question_only_audit"] = fresh_audit
                record["final_blind_issues"] = fresh_issues
                if not fresh_issues:
                    final = context_check(current, fresh_audit, attempt, frozen=True)
                    record["final_context_validation"] = final
                    if (final.get("valid") is True and final.get("issues") == []
                            and final.get("questions") == current):
                        return success(current)
                    issues.extend(str(x) for x in final.get("issues", []) if x)
                    if final.get("questions") != current:
                        issues.append("Final check-only validator edited the frozen questions or references.")
                    if final.get("valid") is not True:
                        issues.append("Final check-only context validation did not pass.")
                else:
                    issues.extend(fresh_issues)
            except PipelineError as exc:
                fail(str(exc))
        if unchanged_text:
            issues.extend(blind_issues)
        elif not context_ok:
            issues.append("Revised questions did not pass the fresh audit and frozen context check.")
        if not issues:
            issues.append("Context validation did not pass or returned a malformed issues list.")
        record["outcome_issues"] = issues[:]
    fail("; ".join(issues) or "unspecified validation failure")


def command_questions(args: argparse.Namespace) -> int:
    question_prompt, question_verify_prompt = question_prompts_for_group(args.group)
    repair_variants = getattr(args, "repair_variant_context", False)
    audit_only = getattr(args, "audit_only", False)
    is_math = args.group == MATHEMATICS_ALGORITHM_GROUP
    if repair_variants and not is_math:
        raise PipelineError("--repair-variant-context requires the mathematics_algorithm_conflicts group.")
    backup_dir = PROJECT_ROOT / "backups" / (
        "math_question_context_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    api_key = require_openrouter_api_key()
    request_limiter = make_openrouter_limiter(args)
    written = 0
    cleared_total = 0
    failures = 0
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    case_paths = iter_case_paths(dataset_dir, args.case_id)

    def run_case(case_path: Path) -> tuple[str, int, str]:
        case = load_case(case_path)
        require_writable_case(case, case_path)
        updated = copy.deepcopy(case)
        # A shared scope serves only videos that inherit case-level questions.
        # Each variant owns its facts/questions and is authored independently.
        scopes = []
        shared_videos = [
            video for video in updated["videos"]
            if video.get("variant_context") is None
        ]
        if shared_videos and not repair_variants:
            scopes.append(("case", updated, shared_videos, None))
        for video in updated["videos"]:
            variant = video.get("variant_context")
            if variant is not None:
                scopes.append((video["video_id"], variant, [video], video))

        cleared = 0
        generated = []
        selected_videos = set(getattr(args, "video_id", None) or [])
        missing = selected_videos - {v["video_id"] for v in updated["videos"]}
        if missing:
            raise PipelineError("Video IDs not found: " + ", ".join(sorted(missing)))
        for scope_id, owner, affected_videos, context_video in scopes:
            if selected_videos and not any(v["video_id"] in selected_videos for v in affected_videos):
                continue
            if owner["questions"] and not args.force and not repair_variants and not audit_only:
                continue
            context = question_case_context(updated, context_video)
            old_questions = owner["questions"]
            if audit_only and not old_questions:
                raise PipelineError(f"No existing questions to audit in scope {scope_id}.")
            preserve_existing = (repair_variants or audit_only) and bool(old_questions)
            response = {}
            if preserve_existing:
                authored_questions = [{
                    "question_en": q["text_en"],
                    "conflict_video_reference_en": q["conflict_video_reference_en"],
                    "normal_control_reference_en": q["normal_control_reference_en"],
                } for q in old_questions]
            else:
                authored, response = openrouter_json(
                    messages=[
                        {"role": "system", "content": question_prompt},
                        {"role": "user", "content": json.dumps(
                            {"case_design": context}, ensure_ascii=False,
                        )},
                    ],
                    model=AUTHOR_JUDGE_MODEL,
                    schema_name="knowledge_conflict_question_authoring",
                    schema=QUESTION_OUTPUT_SCHEMA,
                    api_key=api_key,
                    timeout=args.timeout,
                    max_retries=args.max_retries,
                    request_limiter=request_limiter,
                )
                authored_questions = authored.get("questions")
            if not isinstance(authored_questions, list):
                raise PipelineError("Luna Pro did not return questions.")
            receipt = {}
            verified_questions = verify_authored_questions(
                authored_questions,
                case_context=context,
                system_prompt=question_verify_prompt,
                api_key=api_key,
                timeout=args.timeout,
                max_repairs=args.max_repairs,
                max_retries=args.max_retries,
                request_limiter=request_limiter,
                require_self_contained=is_math,
                preserve_count=preserve_existing,
                audit_only=audit_only,
                audit_receipt=receipt,
            )
            questions = authored_questions_to_questions(verified_questions)
            if preserve_existing:
                # Retain legacy IDs/pair metadata so this is a context repair,
                # not an implicit migration to different question identities.
                questions = [dict(old, text_en=new["text_en"],
                                  conflict_video_reference_en=new["conflict_video_reference_en"],
                                  normal_control_reference_en=new["normal_control_reference_en"])
                             for old, new in zip(old_questions, questions)]
                validate_questions(
                    questions,
                    allow_question_only_results=scope_id == "case",
                )
            if questions != old_questions:
                cleared += sum(
                    len(question.get("question_only_results", []))
                    for question in old_questions
                )
                for question in questions:
                    question.pop("question_only_results", None)
            owner["questions"] = questions
            if questions == old_questions and not receipt:
                continue
            if receipt:
                receipt["scope_fingerprint"] = question_scope_fingerprint(owner, context)
                owner["question_audit"] = receipt
            if questions != old_questions:
                for video in affected_videos:
                    cleared += len(video["qa_results"])
                    video["qa_results"] = []
            generated.append(
                f"{scope_id}: {len(questions)} question(s), request "
                f"{response.get('id') or '(no request id)'}"
            )

        if not generated:
            return (
                "skipped", 0,
                f"No question changes needed in selected scopes: {case_path}",
            )
        # Commit once: a failed variant must not leave a half-updated case.
        updated["schema_version"] = CASE_SCHEMA_VERSION
        validate_case(updated)
        if repair_variants or audit_only:
            atomic_write_json(backup_dir / case_path.name, case)
        atomic_write_json(case_path, updated)
        return "written", cleared, (
            f"Wrote questions for {updated['case_id']} "
            f"({'; '.join(generated)}); cleared {cleared} QA result(s)."
        )

    workers = min(args.case_workers, len(case_paths))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_case, path): path for path in case_paths}
        for future in as_completed(futures):
            case_path = futures[future]
            try:
                outcome, cleared, message = future.result()
            except PipelineError as exc:
                failures += 1
                print(
                    f"Error writing questions for {case_path.stem}: {exc}",
                    file=sys.stderr,
                )
                continue
            written += outcome == "written"
            cleared_total += cleared
            print(message)
    print(
        f"Wrote questions for {written} case(s); "
        f"cleared {cleared_total} QA result(s)."
    )
    if repair_variants and written:
        print(f"Original cases backed up to {backup_dir}")
    if cleared_total:
        print(
            "Derived outputs are now stale; rerun qa-judge and summarize."
        )
    return 1 if failures else 0
