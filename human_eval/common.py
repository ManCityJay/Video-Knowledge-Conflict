"""Small standard-library helpers shared by the offline audit commands."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
LABELS = ("context_grounded", "knowledge_trapped", "ambiguous_or_unjudgeable")
STATUSES = (*LABELS, "unable_to_assess")


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    with Path(path).open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def verify_run(run):
    run = Path(run).resolve()
    manifest = read_json(run / "manifest.json")
    for name, expected in manifest["files"].items():
        path = run / name
        if not within(path, run) or file_hash(path) != expected:
            raise ValueError(f"Frozen audit input changed: {name}")
    return manifest


def choose_judge(tasks, seed):
    """One existing response per QA, deterministic and independent of verdict."""
    available = [t for t in tasks if t.get("result")]
    eligible = [t for t in available if not t["errors"]] or available
    if not eligible:
        raise ValueError("No existing model response for sampled QA")
    return min(eligible, key=lambda t: digest([seed, "one_judge", t["qa_key"], t["id"]]))


def read_tasks(run):
    run = Path(run)
    tasks = read_jsonl(run / "tasks.jsonl")
    selection = run / "judge_selection.json"
    if not selection.exists():
        return tasks
    spec = read_json(selection)
    if spec["tasks_sha256"] != file_hash(run / "tasks.jsonl"):
        raise ValueError("Judge selection belongs to a different task bundle")
    selected = spec["task_ids"]
    judges = [t for t in tasks if t["kind"] == "judge" and t["id"] in selected]
    expected = {t["qa_key"] for t in tasks if t["kind"] == "judge"}
    if len(judges) != len(selected) or len(judges) != len(expected) or {t["qa_key"] for t in judges} != expected:
        raise ValueError("Judge selection must contain exactly one response per sampled QA")
    return [t for t in tasks if t["kind"] == "qa" or t["id"] in selected]
