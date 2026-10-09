#!/usr/bin/env python3
"""Freeze unseen original-case physics/chemistry pairs, without outcome selection."""
import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcd_v1.storage import write_json


def build_manifest(case_dir, pilot, data_root):
    excluded = {i["case_id"] for i in pilot["items"]}
    counts = collections.Counter()
    conflicts, controls = [], {}
    source_hashes = {}
    def usable(v):
        if v.get("status") != "ready" or v.get("human_review") == "rejected" or not v.get("local_path"):
            return False
        return (data_root / v["local_path"]).is_file()
    for path in sorted(case_dir.glob("*.json")):
        data = path.read_bytes()
        case = json.loads(data)
        if case["case_id"] in excluded:
            counts["pilot_cases_excluded"] += 1
            continue
        candidates = [v for v in case["videos"] if v["role"] == "control" and usable(v) and not v.get("variant_context")]
        if len(candidates) != 1:
            counts["cases_without_unique_ready_control"] += 1
            continue
        control = candidates[0]
        source_hashes[str(path.resolve())] = hashlib.sha256(data).hexdigest()
        for video in case["videos"]:
            if video["role"] != "conflict":
                continue
            if video.get("variant_context"):
                counts["variant_videos_excluded"] += 1
                continue
            if not usable(video):
                counts["unusable_conflict_videos"] += 1
                continue
            for q in case["questions"]:
                if not all(q.get(k, "").strip() for k in ("text_en", "conflict_video_reference_en", "normal_control_reference_en")):
                    counts["questions_without_text_or_references"] += 1
                    continue
                pair = f"pair_{len(conflicts)+1:04d}"
                common = {"case_id": case["case_id"], "case_file": str(path.resolve()),
                          "question_id": q["question_id"], "question": q["text_en"], "split": "heldout"}
                key = (str((data_root / control["local_path"]).resolve()), q["text_en"])
                if key not in controls:
                    controls[key] = {**common, "id": f"control_{len(controls)+1:04d}",
                                     "video": key[0], "video_id": control["video_id"], "role": "control",
                                     "reference": q["normal_control_reference_en"],
                                     "human_review": control.get("human_review"), "pairs": []}
                elif controls[key]["reference"] != q["normal_control_reference_en"]:
                    raise ValueError("Conflicting references for identical control video/question")
                controls[key]["pairs"].append(pair)
                conflicts.append({**common, "id": f"conflict_{len(conflicts)+1:04d}",
                                  "video": str((data_root / video["local_path"]).resolve()),
                                  "video_id": video["video_id"], "role": "conflict",
                                  "reference": q["conflict_video_reference_en"],
                                  "human_review": video.get("human_review"), "pairs": [pair],
                                  "control_id": controls[key]["id"]})
    if not conflicts:
        raise ValueError("No eligible held-out pairs")
    items = conflicts + list(controls.values())
    return {"schema": "mcd_heldout_v1", "excluded_pilot_cases": sorted(excluded),
            "source_case_sha256": source_hashes, "selection_counts": dict(counts),
            "counts": {"cases": len({i["case_id"] for i in conflicts}),
                       "conflict_questions": len(conflicts), "unique_control_questions": len(controls),
                       "total": len(items)},
            "note": "All eligible original-case pairs outside pilot cases. No historical answer filtering. Variants and rejected videos excluded. Pending video review allowed. Control deduplicated by video path + exact question. Reference-based review is provisional, not verified video accuracy.",
            "items": items}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--pilot", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    manifest = build_manifest(a.data_root / "dataset/cases/classic_physics_chemistry_experiments",
                              json.loads(a.pilot.read_text()), a.data_root)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(a.output, manifest)
    print(json.dumps(manifest["counts"], indent=2))
    print(json.dumps(manifest["selection_counts"], indent=2))


if __name__ == "__main__":
    main()
