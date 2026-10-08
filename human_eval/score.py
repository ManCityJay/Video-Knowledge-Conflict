"""Score human QA answers offline or with the existing judge, outside the UI."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

from .common import LABELS, digest, now, read_jsonl, verify_run
from .storage import Store


def normalize(text):
    return re.sub(r"\W+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def answer_key(task, answer):
    return digest({"answer": answer, "question": task["qa_input"]["question"], "references": task["references"]})


def exact_score(task, answer):
    """Only exact normalized references can be scored without semantic guessing."""
    value = normalize(answer)
    matches = [label for key, label in (("conflict", "context_grounded"), ("normal", "knowledge_trapped"))
               if value and value == normalize(task["references"][key])]
    return {"label": matches[0], "method": "reference_exact"} if len(matches) == 1 else None


def scores_for(store, who):
    state = store.state(who)
    with store.connection() as db:
        saved = {(r["task_id"], r["answer_hash"]): json.loads(r["data"])
                 for r in db.execute("SELECT * FROM qa_scores WHERE annotator=?", (who,))}
    result = {}
    for tid, task in store.tasks.items():
        entry = state.get((tid, "answer"))
        if task["kind"] != "qa" or not entry or task["errors"]:
            continue
        answer = entry.get("answer", "")
        if not answer:
            continue
        value = saved.get((tid, answer_key(task, answer))) or exact_score(task, answer)
        if value:
            result[tid] = value
    return result


def score(run, *, backend="references", annotator=None, model=None):
    run = Path(run).resolve()
    verify_run(run)
    store = Store(run / "annotations.sqlite", read_jsonl(run / "tasks.jsonl"))
    with store.connection() as db:
        people = [r[0] for r in db.execute("SELECT DISTINCT annotator FROM submissions WHERE stage='answer'")]
    if annotator:
        store.check_annotator(annotator)
        people = [annotator]
    scorer = None
    for who in people:
        existing = scores_for(store, who)
        for (tid, stage), submission in store.state(who).items():
            if stage != "answer" or tid in existing:
                continue
            task = store.tasks[tid]
            answer = submission.get("answer", "")
            if not answer or task["errors"] or backend != "llm":
                continue
            if scorer is None:
                # No provider initialization, credentials or calls until explicitly requested.
                from .adapter import JUDGE_SYSTEM_PROMPT, JUDGMENT_SCHEMA
                from vconflict_pipeline.settings import AUTHOR_JUDGE_MODEL
                from vconflict_pipeline.transport import openrouter_json, require_openrouter_api_key
                scorer = (JUDGE_SYSTEM_PROMPT, JUDGMENT_SCHEMA, openrouter_json, require_openrouter_api_key())
                model = model or AUTHOR_JUDGE_MODEL
            system, schema, request, api_key = scorer
            refs = task["references"]
            payload = {"video_role": "conflict", "question": task["qa_input"]["question"],
                       "final_answer": answer, "normal_fact": refs["facts"]["normal_fact_en"],
                       "intended_video_fact": refs["facts"]["intended_video_fact_en"],
                       "conflict_video_reference": refs["conflict"], "normal_control_reference": refs["normal"]}
            result, response = request(messages=[{"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                model=model, schema_name="human_qa_judgment", schema=schema, api_key=api_key,
                timeout=120, max_retries=2)
            if result.get("verdict") not in LABELS:
                raise ValueError("Judge returned an invalid verdict")
            scored = {"label": result["verdict"], "method": "llm", "model": model,
                      "response": result, "request_id": response.get("id"), "input": payload, "system": system}
            with store.connection() as db:
                db.execute("INSERT OR IGNORE INTO qa_scores VALUES (?,?,?,?,?)",
                    (who, tid, answer_key(task, answer), json.dumps(scored, ensure_ascii=False), now()))
        count = len(scores_for(store, who))
        answered = sum(stage == "answer" for _, stage in store.state(who))
        print(f"{who}: scored {count}/{answered}; unresolved answers are never counted as success")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--backend", choices=("references", "llm"), default="references")
    parser.add_argument("--annotator")
    parser.add_argument("--model")
    args = parser.parse_args()
    score(args.run, backend=args.backend, annotator=args.annotator, model=args.model)


if __name__ == "__main__":
    main()
