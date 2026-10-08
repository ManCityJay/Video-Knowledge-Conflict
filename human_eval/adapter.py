"""Read-only adapter for the repository's compact case schema.

Only pure prompt/schema/selection helpers are imported; no command or provider is
invoked. Historical requests were not persisted, so reconstructed messages are
explicitly marked as such and the source code hashes are frozen by prepare.
"""
from __future__ import annotations

import sys
import hashlib
from pathlib import Path

from .common import ROOT, digest, file_hash, within

sys.path.insert(0, str(ROOT / "scripts"))
from vconflict_pipeline.core import (JUDGMENT_SCHEMA, canonical_verdict,
                                    video_case_context, qa_result_input_mode)
from vconflict_pipeline.evaluation import JUDGE_SYSTEM_PROMPT
from vconflict_pipeline.integrity import video_selected, judgment_fingerprint
from vconflict_pipeline.qa import (_video_question_prompt, _description_prompt,
                                  _cosmos_prompt, qa_result_thinking_effort)
from vconflict_pipeline.settings import FAIRY_TALE_GROUP, COSMOS_QA_MODEL, QWEN_QA_MODEL


def profile(result):
    return {"model": result.get("model"), "input_mode": qa_result_input_mode(result),
            "thinking_effort": qa_result_thinking_effort(result),
            "based": result.get("based", False),
            "work_title_prefix": result.get("work_title_prefix")}


def profile_id(value):
    return digest(value)[:16]


def matches(result, config):
    p = profile(result)
    return (p["input_mode"] == config["input_mode"]
            and (not config["judge_models"] or p["model"] in config["judge_models"])
            and (config["judge_efforts"] is None or p["thinking_effort"] in config["judge_efforts"])
            and (config["judge_based"] is None or p["based"] == config["judge_based"])
            and (config["judge_work_title_prefix"] is None
                 or p["work_title_prefix"] is config["judge_work_title_prefix"]))


def media_path(video):
    path = (ROOT / video["local_path"]).resolve()
    if not within(path, ROOT / "videos"):
        raise ValueError("Video must remain inside the repository videos directory")
    return path


def input_snapshot(context, question, p, *, context_text=None):
    warnings = ["Messages reconstructed from frozen pipeline source; original request body was not saved."]
    errors = []
    if p["input_mode"] == "description":
        if not isinstance(context_text, str) or not context_text.strip():
            errors.append("Description context is missing")
            context_text = ""
        prompt = _description_prompt(context_text, question["text_en"], based=p["based"])
    else:
        prompt = _video_question_prompt(
            question["text_en"], work_title=context["title"].split(":", 1)[0].strip(),
            work_title_prefix=p["work_title_prefix"] is True, based=p["based"])
    messages = []
    sampling = "Provider-internal frame/audio processing was not recorded. Exact internal frames cannot be recovered."
    model = p["model"] or ""
    if model == COSMOS_QA_MODEL:
        prompt = _cosmos_prompt(prompt, p["thinking_effort"])
        messages.append({"role": "system", "content": "You are a helpful assistant."})
        sampling = "Video processor: fps=4, do_sample_frames=true. Exact processed frames were not persisted."
    elif model not in {QWEN_QA_MODEL, "kimi-k3"} and not model.startswith("google/gemini-"):
        errors.append(f"Unsupported model prompt adapter: {model}")
    if p["input_mode"] == "video":
        if model == QWEN_QA_MODEL:
            content = [{"video": "asset:video", "fps": 2}, {"text": prompt}]
            sampling = "DashScope input fps=2. SDK/provider-selected frames were not persisted."
        else:
            content = [{"type": "video_url", "video_url": {"url": "asset:video"}},
                       {"type": "text", "text": prompt}]
        warnings.append(sampling)
    else:
        content = [{"text": prompt}] if model == QWEN_QA_MODEL else prompt
    messages.append({"role": "user", "content": content})
    return {"question": question["text_en"], "prompt": prompt, "messages": messages,
            "input_mode": p["input_mode"], "profile": p, "provenance": "reconstructed",
            "warnings": warnings, "errors": errors}


def judge_snapshot(context, video, question, result):
    return {"system": JUDGE_SYSTEM_PROMPT, "response_schema": JUDGMENT_SCHEMA,
            "input": {"video_role": video["role"], "question": question["text_en"],
                      "final_answer": result.get("final_answer"),
                      "normal_fact": context["conflict_spec"]["normal_fact_en"],
                      "intended_video_fact": context["conflict_spec"]["intended_video_fact_en"],
                      "conflict_video_reference": question["conflict_video_reference_en"],
                      "normal_control_reference": question["normal_control_reference_en"]},
            "provenance": "reconstructed", "video_sent_to_judge": False,
            "judged_field": "final_answer"}



def description_errors(video, media):
    description = video.get("description") or {}
    observation = video.get("video_observation") or {}
    if not description.get("context_en"):
        return ["Missing description context"]
    if description.get("source") == "video":
        if (not observation or not media.get("sha256")
                or observation.get("source_sha256") != media["sha256"]
                or description.get("source_sha256") != media["sha256"]
                or description["context_en"] != observation.get("context_en", observation.get("summary_en"))):
            return ["Video-derived description is stale or not bound to observed pixels"]
    else:
        expected = hashlib.sha256(video.get("seedance_prompt_en", "").encode("utf-8")).hexdigest()
        if (observation or video.get("require_video_observation")
                or description.get("source_sha256") != expected):
            return ["Prompt-derived description is stale or requires visual evidence"]
    return []


def result_quality(case, video, question, result, media):
    """Validate bindings without rehashing the same video for every model answer."""
    errors, warnings = [], []
    if result.get("question") != question["text_en"]:
        errors.append("Stored question differs from current question")
    if not isinstance(result.get("final_answer"), str) or not result["final_answer"].strip():
        errors.append("Missing final_answer")
    p = profile(result)
    context = video_case_context(case, video)
    if p["input_mode"] == "video":
        content = media.get("sha256")
        if not content:
            errors.append("Missing video file")
    else:
        errors += description_errors(video, media)
        content = (video.get("description") or {}).get("context_en")
        if not content or content != result.get("context_text_en"):
            errors.append("Stored description differs from current context")
    binding = {"version": 1, "input": p["input_mode"], "content": content,
               "question": question["text_en"], "question_id": question["question_id"],
               "title": context["title"].split(":", 1)[0].strip() if p["work_title_prefix"] else None}
    if p["based"]:
        binding["based"] = True
    if result.get("input_fingerprint"):
        if result["input_fingerprint"] != digest(binding):
            errors.append("QA input fingerprint is stale")
    else:
        warnings.append("Legacy QA has no input fingerprint; historical media identity cannot be verified")
    judgment = result.get("judgment") or {}
    if not judgment:
        errors.append("Missing LLM judgment")
    elif canonical_verdict(judgment.get("verdict")) not in {
            "context_grounded", "knowledge_trapped", "ambiguous_or_unjudgeable"}:
        errors.append("Unknown LLM verdict")
    if judgment.get("input_fingerprint"):
        if judgment["input_fingerprint"] != judgment_fingerprint(case, video, result):
            errors.append("Judge input fingerprint is stale")
    else:
        warnings.append("Legacy judge has no input fingerprint")
    return errors, warnings
