"""Activate one answer per frozen judge QA without changing history or the database."""
import argparse
from collections import defaultdict
from pathlib import Path
from .common import choose_judge, file_hash, now, read_jsonl, read_tasks, verify_run, write_json

def select(run):
    run = Path(run)
    manifest = verify_run(run)
    target = run / "judge_selection.json"
    if target.exists():
        read_tasks(run)
        return
    groups = defaultdict(list)
    for task in read_jsonl(run / "tasks.jsonl"):
        if task["kind"] == "judge":
            groups[task["qa_key"]].append(task)
    chosen = [choose_judge(tasks, manifest["config"]["seed"]) for _, tasks in sorted(groups.items())]
    if any(t["errors"] for t in chosen):
        raise ValueError("Some sampled QA have no usable response; keep current selection unchanged")
    write_json(target, {"created_at": now(), "tasks_sha256": file_hash(run / "tasks.jsonl"),
                       "policy": "one seeded usable response per existing sampled QA; independent of verdict",
                       "task_ids": [t["id"] for t in chosen]})
    read_tasks(run)
    print(f"Activated {len(chosen)} judge items. Original tasks and annotations preserved.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    select(parser.parse_args().run)
