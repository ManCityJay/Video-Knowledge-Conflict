"""Build an immutable, portable audit bundle. Run: python -m human_eval.prepare."""
from __future__ import annotations

import argparse
import collections
import random
import shutil
from pathlib import Path

from . import adapter
from .common import (HERE, ROOT, digest, file_hash, now, read_json, write_json,
                     write_jsonl, within, choose_judge)


STANDARD_GROUPS = (
    "classic_fairy_tale_film_conflicts",
    "classic_physics_chemistry_experiments",
    "mathematics_algorithm_conflicts",
    "real_world_commonsense_conflicts",
)

def draw(units, count, seed, task, group):
    ordered = sorted(units, key=lambda row: row["key"])
    rng = random.Random(digest([seed, task, group]))
    return rng.sample(ordered, min(count, len(ordered)))


def validate_config(config):
    if type(config["per_group"]) is not int or config["per_group"] < 1:
        raise ValueError("per_group must be a positive integer")
    if config["input_mode"] not in {"video", "description"}:
        raise ValueError("This conflict audit supports video or description input")
    if config["video_scope"] not in {None, "all", "qualified"}:
        raise ValueError("video_scope must be null, all or qualified")
    for key in ("qa_based", "qa_work_title_prefix"):
        if type(config[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    for key in ("judge_based", "judge_work_title_prefix"):
        if config[key] is not None and type(config[key]) is not bool:
            raise ValueError(f"{key} must be boolean or null")
    for key in ("groups", "judge_models"):
        if not isinstance(config[key], list) or not all(isinstance(x, str) for x in config[key]):
            raise ValueError(f"{key} must be a string list")
    if config["judge_efforts"] is not None and not isinstance(config["judge_efforts"], list):
        raise ValueError("judge_efforts must be a list or null")


def inventory(dataset, config):
    groups = sorted(p for p in dataset.iterdir() if p.is_dir())
    selected_groups = config["groups"] or STANDARD_GROUPS
    if selected_groups:
        missing = set(selected_groups) - {p.name for p in groups}
        if missing:
            raise ValueError(f"Unknown groups: {sorted(missing)}")
        groups = [p for p in groups if p.name in selected_groups]
    if not groups:
        raise ValueError(f"No group directories in {dataset}")
    output, audit = {}, {}
    for group in groups:
        units, seen = [], set()
        counts = collections.Counter()
        for path in sorted(group.glob("*.json")):
            case = read_json(path)
            counts["case_files"] += 1
            if case.get("canonical_case_path"):
                counts["promoted_aliases_excluded"] += 1
                continue
            for video in case["videos"]:
                if video["role"] != "conflict":
                    continue
                if not adapter.video_selected(video, config["input_mode"], config["video_scope"]):
                    counts["videos_outside_scope"] += 1
                    continue
                context = adapter.video_case_context(case, video)
                if not context["questions"]:
                    counts["videos_without_questions"] += 1
                for question in context["questions"]:
                    # A question attached to a different video is a distinct stimulus.
                    key = "/".join([group.name, case["case_id"], video["video_id"], question["question_id"]])
                    if key in seen:
                        raise ValueError(f"Duplicate QA identity: {key}")
                    seen.add(key)
                    results = [r for r in video.get("qa_results", [])
                               if r["question_id"] == question["question_id"] and adapter.matches(r, config)]
                    units.append({"key": key, "group": group.name, "path": path,
                                  "case": case, "video": video, "question": question,
                                  "context": context, "results": results})
        counts["qa_candidates"] = len(units)
        counts["judge_candidates"] = sum(bool(u["results"]) for u in units)
        output[group.name], audit[group.name] = units, dict(counts)
    return output, audit


class Bundle:
    def __init__(self, run):
        self.run = run
        self.media_cache = {}
        self.sources = {}

    def freeze_media(self, video):
        source = adapter.media_path(video)
        if source in self.media_cache:
            return self.media_cache[source]
        errors, warnings = [], []
        asset = {"source": video["local_path"], "asset": None, "sha256": None,
                 "errors": errors, "warnings": warnings}
        if not source.is_file() or source.stat().st_size == 0:
            errors.append("Missing or empty video file")
        else:
            fingerprint = file_hash(source)
            name = f"media/{fingerprint}{source.suffix.lower()}"
            target = self.run / name
            if not target.exists():
                shutil.copyfile(source, target)
            if file_hash(target) != fingerprint:
                raise ValueError(f"Video changed while copying: {source}")
            asset.update(asset=name, sha256=fingerprint)
        obs = video.get("video_observation")
        if obs and obs.get("source_sha256") != asset["sha256"]:
            errors.append("Video observation is bound to different pixels")
        elif video.get("require_video_observation") and not obs:
            errors.append("Required video observation is missing")
        if not obs:
            warnings.append("No file-bound visual observation in source case")
        self.media_cache[source] = asset
        return asset

    def base(self, unit):
        path = unit["path"]
        if path not in self.sources:
            # Freeze the parsed bytes that actually determined the sampled record.
            value = unit["case"]
            if read_json(path) != value:
                raise ValueError(f"Case changed during prepare: {path}")
            source_name = f"sources/{digest(str(path))[:20]}.json"
            write_json(self.run / source_name, value)
            self.sources[path] = {"path": str(path), "snapshot": source_name,
                                  "source_sha256": file_hash(path)}
        q = unit["question"]
        return {"qa_key": unit["key"], "group": unit["group"],
                "case_id": unit["case"]["case_id"], "video_id": unit["video"]["video_id"],
                "question_id": q["question_id"], "source": self.sources[path],
                "media": self.freeze_media(unit["video"]),
                "references": {"conflict": q["conflict_video_reference_en"],
                               "normal": q["normal_control_reference_en"],
                               "facts": unit["context"]["conflict_spec"]}}


def prepare(run, dataset, config):
    validate_config(config)
    run, dataset = Path(run).resolve(), Path(dataset).resolve()
    if not within(run, HERE / "runs"):
        raise ValueError("Run directory must be under human_eval/runs (keeps writes isolated)")
    if run.exists():
        raise ValueError(f"Run already exists; refusing to overwrite samples or annotations: {run}")
    units_by_group, audit = inventory(dataset, config)
    run.mkdir(parents=True)
    for directory in ("media", "sources", "reports", "code"):
        (run / directory).mkdir()
    bundle = Bundle(run)
    tasks, qa_samples, judge_samples = [], [], []
    profiles_by_group = {}
    for group, units in units_by_group.items():
        qa_draw = draw(units, config["per_group"], config["seed"], "qa", group)
        judge_pool = [u for u in units if u["results"]]
        judge_draw = draw(judge_pool, config["per_group"], config["seed"], "judge", group)
        profiles = {adapter.profile_id(adapter.profile(r)): adapter.profile(r)
                    for u in judge_pool for r in u["results"]}
        profiles_by_group[group] = profiles
        audit[group].update(qa_sampled=len(qa_draw), judge_sampled=len(judge_draw),
                            qa_shortfall=max(0, config["per_group"] - len(qa_draw)),
                            judge_shortfall=max(0, config["per_group"] - len(judge_draw)))
        for unit in qa_draw:
            p = {"model": config["qa_model"], "input_mode": config["input_mode"],
                 "thinking_effort": config["qa_effort"], "based": config["qa_based"],
                 "work_title_prefix": config["qa_work_title_prefix"] if group == adapter.FAIRY_TALE_GROUP else False}
            task = bundle.base(unit)
            snapshot = adapter.input_snapshot(unit["context"], unit["question"], p,
                context_text=(unit["video"].get("description") or {}).get("context_en"))
            snapshot["provenance"] = "current_pipeline_prompt_for_human_trial"
            snapshot["warnings"][0] = "Human trial uses the frozen current pipeline prompt and configured model condition."
            errors = list(snapshot["errors"])
            if config["input_mode"] == "video":
                errors += task["media"]["errors"]
            else:
                errors += adapter.description_errors(unit["video"], task["media"])
            task.update(id="qa-" + digest(unit["key"])[:20], kind="qa", qa_input=snapshot,
                        errors=errors, warnings=task["media"]["warnings"] + snapshot["warnings"])
            tasks.append(task)
            qa_samples.append({"qa_key": unit["key"], "group": group, "task_id": task["id"]})
        for unit in judge_draw:
            base = bundle.base(unit)
            task_ids = []
            choices = []
            for pid, p in sorted(profiles.items()):
                candidates = [r for r in unit["results"] if adapter.profile_id(adapter.profile(r)) == pid]
                # Select latest attempt irrespective of its answer or verdict.
                candidates.sort(key=lambda r: (r.get("timestamp", ""), r.get("run_id", "")))
                result = candidates[-1] if candidates else None
                task = {**base, "id": "judge-" + digest([unit["key"], pid])[:20], "kind": "judge",
                        "profile": p, "profile_id": pid, "result": result,
                        "candidate_run_ids": [r.get("run_id") for r in candidates],
                        "judge_input": None, "qa_input": None,
                        "errors": [], "warnings": list(base["media"]["warnings"])}
                if result is None:
                    task["errors"].append("No result for this sampled QA and model condition")
                else:
                    errors, warnings = adapter.result_quality(unit["case"], unit["video"], unit["question"], result, base["media"])
                    task["errors"] += errors + base["media"]["errors"]
                    task["warnings"] += warnings
                    if group == adapter.FAIRY_TALE_GROUP and p["input_mode"] == "video" and p["work_title_prefix"] is None:
                        task["errors"].append("Historical fairy-tale work-title prefix is unknown")
                    task["qa_input"] = adapter.input_snapshot(unit["context"], unit["question"], p,
                        context_text=result.get("context_text_en"))
                    task["errors"] += task["qa_input"]["errors"]
                    task["warnings"] += task["qa_input"]["warnings"]
                    task["judge_input"] = adapter.judge_snapshot(unit["context"], unit["video"], unit["question"], result)
                choices.append(task)
            selected = choose_judge(choices, config["seed"])
            tasks.append(selected)
            task_ids.append(selected["id"])
            judge_samples.append({"qa_key": unit["key"], "group": group, "task_ids": task_ids})
        print(f"{group}: QA {len(qa_draw)}/{len(units)}, judge {len(judge_draw)}/{len(judge_pool)} QA, {len(profiles)} conditions")
    # A deterministic blind display order, unrelated to model output or label.
    random.Random(digest([config["seed"], "display_order"])).shuffle(tasks)
    write_jsonl(run / "tasks.jsonl", tasks)
    write_jsonl(run / "qa_samples.jsonl", qa_samples)
    write_jsonl(run / "judge_samples.jsonl", judge_samples)
    source_code = sorted((ROOT / "scripts" / "vconflict_pipeline").glob("*.py")) + sorted(HERE.glob("*.py"))
    for path in source_code:
        destination = run / "code" / (path.parent.name + "_" + path.name)
        shutil.copyfile(path, destination)
    files = {p.relative_to(run).as_posix(): file_hash(p) for p in sorted(run.rglob("*")) if p.is_file()}
    manifest = {"schema_version": 1, "created_at": now(), "config": config,
                "dataset": str(dataset), "sampling_unit": "group/case_id/video_id/question_id",
                "judge_sampling": "one existing response per sampled QA; deterministic seeded choice among usable latest-per-condition responses, falling back to blocked responses only when none usable; never filter by verdict",
                "inventory": audit, "profiles": profiles_by_group,
                "task_count": len(tasks), "blocked_task_count": sum(bool(t["errors"]) for t in tasks),
                "files": files, "sources": list(bundle.sources.values()),
                "limitations": ["Historical HTTP request bodies and provider-internal frames were not saved.",
                                "Reconstructed prompts and legacy fingerprints are disclosed per task.",
                                "Existing LLM judge is text-only and evaluates final_answer only."]}
    write_json(run / "manifest.json", manifest)
    print(f"Prepared {run}; {manifest['task_count']} annotation items, {manifest['blocked_task_count']} with missing/stale inputs")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset" / "cases")
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    config = read_json(HERE / "config.json")
    custom = read_json(args.config)
    if set(custom) - set(config):
        parser.error(f"Unknown config keys: {sorted(set(custom) - set(config))}")
    config.update(custom)
    try:
        prepare(args.run, args.dataset, config)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"Prepare failed: {exc}\nNo source dataset was modified. Use a new run name after fixing inputs.\n")


if __name__ == "__main__":
    main()
