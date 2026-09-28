#!/usr/bin/env python3
"""Run one Cosmos video question with MCD v1, optionally beside plain greedy."""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from vconflict_pipeline.core import PipelineError, resolve_video_path, video_case_context
from vconflict_pipeline.qa import _cosmos_prompt, _video_question_prompt, extract_final_answer
from vconflict_pipeline.settings import COSMOS_QA_MODEL, PROJECT_ROOT


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path, help="Video path, relative to the current directory or absolute")
    source.add_argument("--case", type=Path, help="Existing case JSON; does not modify the file")
    parser.add_argument("--question", help="Question text, required with --video")
    parser.add_argument("--video-id", help="Required with --case")
    parser.add_argument("--question-id", help="Required with --case")
    parser.add_argument("--work-title", help="Optional title prefix, applied identically to both branches")
    parser.add_argument("--model", default=COSMOS_QA_MODEL, help="HF model ID or local checkpoint directory")
    parser.add_argument("--revision", help="Optional checkpoint revision (also used for the processor)")
    parser.add_argument("--lambda", dest="weight", type=float, default=0.5, help="Text prior weight; 0 = greedy")
    parser.add_argument("--beta", type=float, default=0.1, help="Video plausibility cutoff; 0 = disabled")
    parser.add_argument("--fps", type=float, default=4.0)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=("bfloat16", "float16", "float32"), default="bfloat16")
    parser.add_argument("--compare-baseline", action="store_true", help="Also run plain greedy on the same inputs")
    parser.add_argument("--output", type=Path, help="New JSON file; defaults to results/mcd_v1/<unique ID>.json")
    return parser


def resolve_sample(args):
    metadata = {}
    if args.case:
        if args.question is not None or not args.video_id or not args.question_id:
            raise ValueError("--case requires --video-id and --question-id, and cannot use --question")
        case = json.loads(args.case.read_text(encoding="utf-8-sig"))
        video = next((v for v in case["videos"] if v["video_id"] == args.video_id), None)
        if video is None:
            raise ValueError(f"Unknown video ID: {args.video_id}")
        context = video_case_context(case, video)
        question = next((q for q in context["questions"] if q["question_id"] == args.question_id), None)
        if question is None:
            raise ValueError(f"Unknown question ID: {args.question_id}")
        path = resolve_video_path(video["local_path"], must_exist=True)
        question_text = question["text_en"]
        metadata = {"case_id": case["case_id"], "video_id": args.video_id,
                    "question_id": args.question_id, "video_role": video["role"],
                    "human_review": video.get("human_review")}
    else:
        if not args.question or args.video_id or args.question_id:
            raise ValueError("--video requires --question; IDs are only used with --case")
        path = args.video.resolve()
        question_text = args.question
    if not path.is_file():
        raise ValueError(f"Video file does not exist: {path}")
    if not question_text.strip():
        raise ValueError("Question must not be empty")
    # Only the question/title enter the prompt, never references or annotations.
    prompt = _cosmos_prompt(_video_question_prompt(
        question_text, work_title=args.work_title, work_title_prefix=bool(args.work_title)
    ), thinking_effort=None)
    return path, question_text, prompt, metadata


def messages_for(prompt, video_path=None):
    content = []
    if video_path is not None:
        content.append({"type": "video", "path": str(video_path)})
    content.append({"type": "text", "text": prompt})
    return [{"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": content}]


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not math.isfinite(args.weight) or args.weight < 0:
        parser.error("--lambda must be finite and >= 0")
    if not math.isfinite(args.beta) or not 0 <= args.beta <= 1:
        parser.error("--beta must be between 0 and 1")
    if not math.isfinite(args.fps) or args.fps <= 0 or args.max_new_tokens <= 0:
        parser.error("--fps and --max-new-tokens must be positive")
    try:
        video, question, prompt, sample = resolve_sample(args)
    except (ValueError, KeyError, OSError, PipelineError) as exc:
        parser.error(str(exc))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    output_path = args.output or PROJECT_ROOT / "results" / "mcd_v1" / f"{run_id}.json"
    if output_path.exists():
        parser.error(f"Output already exists; choose a new filename: {output_path}")

    # Lazy imports keep --help and argument validation usable without GPU deps.
    try:
        import torch
        import transformers
        from transformers import AutoProcessor, Cosmos3OmniForConditionalGeneration, GenerationConfig
        from vconflict_pipeline.mcd_v1 import TextPriorContrastiveProcessor
    except ImportError as exc:
        parser.error(f"Install requirements-mcd-v1.txt in the server environment: {exc}")

    torch.manual_seed(0)
    dtype = getattr(torch, args.dtype)
    checkpoint = {"revision": args.revision} if args.revision else {}
    print(f"Loading {args.model} on {args.device} ...", flush=True)
    processor = AutoProcessor.from_pretrained(args.model, **checkpoint)
    model = Cosmos3OmniForConditionalGeneration.from_pretrained(
        args.model, dtype=dtype, device_map=args.device, attn_implementation="sdpa", **checkpoint
    ).eval()
    video_inputs = processor.apply_chat_template(
        messages_for(prompt, video), tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors="pt", fps=args.fps, do_sample_frames=True,
    ).to(model.device, dtype)
    text_inputs = processor.apply_chat_template(
        messages_for(prompt), tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors="pt",
    ).to(model.device, dtype)

    eos = model.generation_config.eos_token_id
    if eos is None:
        eos = processor.tokenizer.eos_token_id
    if eos is None:
        raise ValueError("Checkpoint/tokenizer has no EOS token ID")
    eos_ids = {eos} if isinstance(eos, int) else set(eos)
    pad = processor.tokenizer.pad_token_id
    if pad is None:
        pad = min(eos_ids)
    # Start from a clean config: no inherited sampling, repetition penalties or
    # forced tokens may change the raw expert logits before our combination.
    generation = GenerationConfig(
        do_sample=False, num_beams=1, max_new_tokens=args.max_new_tokens,
        eos_token_id=eos, pad_token_id=pad, use_cache=True,
    )
    prompt_length = video_inputs["input_ids"].shape[1]
    result = {
        "method": "mcd_v1", "formula": "log_p_video - lambda * log_p_text",
        "run_id": run_id, "sample": sample, "video": str(video), "question": question,
        "prompt": prompt, "model": args.model, "requested_revision": args.revision,
        "resolved_revision": getattr(model.config, "_commit_hash", None),
        "lambda": args.weight, "beta": args.beta, "fps": args.fps,
        "thinking_effort": "none", "dtype": args.dtype, "device": args.device,
        "max_new_tokens": args.max_new_tokens, "torch_version": torch.__version__,
        "transformers_version": transformers.__version__, "negative_branch_cache": False,
        "video_prompt_tokens": prompt_length,
        "text_prompt_tokens": text_inputs["input_ids"].shape[1],
        "video_grid_thw": video_inputs["video_grid_thw"].tolist(), "runs": {},
    }

    def generate(weight, *, apply_cd):
        model.model.rope_deltas = None
        logits_processor = TextPriorContrastiveProcessor(
            model, text_inputs, prompt_length, weight=weight, beta=args.beta,
        )
        start = time.perf_counter()
        with torch.inference_mode():
            sequences = model.generate(
                **video_inputs, generation_config=copy.deepcopy(generation),
                logits_processor=[logits_processor] if apply_cd else [],
            )
        token_ids = sequences[0, prompt_length:].tolist()
        raw = processor.tokenizer.decode(token_ids, skip_special_tokens=True,
                                         clean_up_tokenization_spaces=False)
        finish = "eos" if token_ids and token_ids[-1] in eos_ids else "length"
        parsed, parse_error = None, None
        try:
            parsed = extract_final_answer(raw)
        except PipelineError as exc:
            parse_error = str(exc)
        return {"lambda": weight, "raw_answer": raw, "final_answer": parsed,
                "parse_error": parse_error, "finish_reason": finish,
                "status": "truncated" if finish == "length" else "parse_error" if parse_error else "ok",
                "generated_token_ids": token_ids, "generated_tokens": len(token_ids),
                "seconds": round(time.perf_counter() - start, 3)}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    jobs = [("baseline", 0.0)] if args.compare_baseline else []
    jobs.append(("mcd_v1", args.weight))
    try:
        for name, weight in jobs:
            print(f"Running {name} (lambda={weight}) ...", flush=True)
            answer = generate(weight, apply_cd=name == "mcd_v1")
            result["runs"][name] = answer
            failed = failed or answer["status"] != "ok"
            print(f"[{name}] {answer['raw_answer']}\nstatus={answer['status']}", flush=True)
        if args.compare_baseline and args.weight == 0:
            result["lambda_zero_matches"] = (
                result["runs"]["baseline"]["generated_token_ids"]
                == result["runs"]["mcd_v1"]["generated_token_ids"]
            )
            failed = failed or not result["lambda_zero_matches"]
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        failed = True
        print(f"Generation failed: {exc}", file=sys.stderr)
    finally:
        # Exclusive creation prevents replacing an existing experiment file.
        with output_path.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"Saved: {output_path}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
