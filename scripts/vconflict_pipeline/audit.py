"""Offline structural audit; never calls a provider or grants review approval."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .core import (PipelineError, atomic_write_json, grouped_dir, iter_case_paths,
                   load_case, utc_now, video_case_context)
from .evidence import observed_summary
from .integrity import (description_is_current, qa_is_current, judgment_is_current,
                        question_scope_fingerprint, video_selected)
from .settings import PROJECT_ROOT, DEFAULT_SOURCE_CASE_DIR


def audit_cases(paths: list[Path], *, group: str | None = None) -> dict:
    from .authoring import question_case_context
    counts = Counter()
    findings = []
    physical_paths = set()

    def note(level, code, entity, detail):
        findings.append(dict(level=level, code=code, entity=entity, detail=detail))

    for path in paths:
        try:
            case = load_case(path)
        except (PipelineError, OSError, ValueError) as exc:
            note("error", "invalid_case", str(path), str(exc))
            continue
        counts["cases"] += 1
        cid = case["case_id"]
        if path.stem != cid:
            note("error", "case_filename", str(path), cid)
        source = grouped_dir(DEFAULT_SOURCE_CASE_DIR, group) / (cid + ".md")
        if not source.is_file():
            note("error", "missing_source", cid, str(source))
        scopes = [(case, None)] if any(not v.get("variant_context") for v in case["videos"]) else []
        for video in case["videos"]:
            entity = cid + "/" + video["video_id"]
            counts["videos"] += 1
            counts["status_" + video["status"]] += 1
            local = (PROJECT_ROOT / video["local_path"]).resolve()
            if group and Path(video["local_path"]).parts[2] != group:
                note("error", "wrong_video_group", entity, video["local_path"])
            if local in physical_paths:
                note("error", "duplicate_file_binding", entity, str(local))
            physical_paths.add(local)
            qualified = "qualified" in local.parts
            if qualified:
                counts["qualified_" + video["role"]] += 1
                counts["qualified_review_" + video["human_review"]] += 1
                if video["human_review"] != "verified":
                    note("warning", "qualified_review_unverified", entity, video["human_review"])
                if local.stem != video["video_id"] and video["role"] == "conflict":
                    note("error", "qualified_video_filename", entity, str(local))
                elif local.stem != video["video_id"]:
                    note("info", "legacy_control_filename", entity,
                         "The legacy control filename is resolved through local_path; no renumbering is needed.")
            if video["status"] == "ready" and not local.is_file():
                note("error", "missing_video", entity, str(local))
            if video_selected(video, "video"):
                counts["default_video_targets_" + video["role"]] += 1
                if not video_case_context(case, video)["questions"]:
                    note("error", "missing_questions", entity, "No questions in the effective video scope.")
            if video.get("video_observation"):
                counts["video_observations"] += 1
            try:
                if video["status"] == "ready":
                    observed_summary(video)
                if video.get("description"):
                    counts["description_" + video["description"]["source"]] += 1
                    if not description_is_current(video):
                        note("error", "stale_description", entity, "Description no longer matches its source.")
            except (PipelineError, OSError) as exc:
                note("error", "invalid_evidence", entity, str(exc))
            for result in video["qa_results"]:
                counts["qa_results"] += 1
                if not qa_is_current(case, video, result):
                    note("warning", "stale_qa", entity, result["run_id"])
                elif result.get("judgment") and not judgment_is_current(case, video, result):
                    note("warning", "stale_judgment", entity, result["run_id"])
            variant = video.get("variant_context")
            if variant is not None:
                counts["variant_scopes"] += 1
                scopes.append((variant, video))
                source_name = variant.get("source_variant_case_path")
                if source_name:
                    source_path = (PROJECT_ROOT / source_name).resolve()
                    if not source_path.is_relative_to(PROJECT_ROOT.resolve()):
                        note("error", "unsafe_variant_path", entity, source_name)
                    elif not source_path.is_file():
                        note("error", "missing_variant_source", entity, source_name)
                    else:
                        try:
                            historical = load_case(source_path)
                            if historical["conflict_spec"] != variant["conflict_spec"]:
                                note("warning", "historical_facts_differ", entity, source_name)
                            if historical["questions"] != variant["questions"]:
                                note("info", "historical_questions_differ", entity,
                                     "Canonical variant_context is authoritative; historical source is not an editable mirror.")
                        except (PipelineError, ValueError, OSError) as exc:
                            note("error", "invalid_variant_source", entity, str(exc))
                if qualified and (video.get("description") or {}).get("source") != "video":
                    counts["qualified_variant_prompt_descriptions"] += 1
        for owner, video in scopes:
            entity = cid + ("/" + video["video_id"] if video else "/shared")
            if not owner["questions"]:
                continue
            counts["question_scopes"] += 1
            receipt = owner.get("question_audit")
            if not receipt:
                counts["question_audit_missing"] += 1
                note("warning", "question_audit_missing", entity,
                     "No persisted independent model audit receipt; existing text is not proof of an audit.")
                continue
            if not isinstance(receipt, dict):
                counts["question_audit_stale"] += 1
                note("warning", "question_audit_stale", entity, "Malformed audit receipt.")
                continue
            try:
                valid = (receipt.get("method") == "independent_model" and receipt.get("status") == "passed"
                         and (group != "mathematics_algorithm_conflicts" or receipt.get("question_only") is True)
                         and bool(receipt.get("checks"))
                         and receipt.get("scope_fingerprint") == question_scope_fingerprint(owner, question_case_context(case, video)))
            except (PipelineError, OSError):
                valid = False
            counts["question_audit_current" if valid else "question_audit_stale"] += 1
            if not valid:
                note("warning", "question_audit_stale", entity, "Audit receipt does not certify this current scope.")
    return {"generated_at": utc_now(), "group": group, "offline": True,
            "counts": dict(counts), "errors": sum(x["level"] == "error" for x in findings),
            "warnings": sum(x["level"] == "warning" for x in findings), "findings": findings}


def command_audit(args) -> int:
    paths = iter_case_paths(grouped_dir(args.dataset_dir, args.group), args.case_id)
    report = audit_cases(paths, group=args.group)
    atomic_write_json(args.output, report)
    print(f"Offline audit: {report['counts'].get('cases', 0)} cases; "
          f"{report['errors']} errors; {report['warnings']} warnings. Report: {args.output}")
    return 1 if report["errors"] or (args.strict and report["warnings"]) else 0
