"""Behavioral checks for blinding, sampling, provenance and metric denominators."""
from __future__ import annotations

import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import adapter
from .app import Audit, make_server
from .common import HERE, digest, file_hash, read_json, read_jsonl, write_json
from .prepare import STANDARD_GROUPS, draw, inventory, prepare
from .report import judge_stats, qa_stats, report
from .score import scores_for


class HumanEvalTests(unittest.TestCase):
    def setUp(self):
        (HERE / "runs").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="test_", dir=HERE / "runs")
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "dataset"
        self.group = self.dataset / "sample_group"
        self.group.mkdir(parents=True)
        self.media = self.root / "sample.mp4"
        self.media.write_bytes(bytes(range(256)))
        self.config = read_json(HERE / "config.json")
        self.config["groups"] = ["sample_group"]
        self.config["per_group"] = 2
        self.case = {
            "case_id": "case001", "title": "Example: Different event",
            "conflict_spec": {"normal_fact_en": "Normal fact SECRET_NORMAL", "intended_video_fact_en": "Conflict fact SECRET_CONFLICT"},
            "questions": [], "videos": []}
        for i in range(3):
            qid = f"q{i}"
            q = {"question_id": qid, "text_en": f"What happens in example {i}?",
                 "conflict_video_reference_en": "SECRET_CONFLICT", "normal_control_reference_en": "SECRET_NORMAL"}
            self.case["questions"].append(q)
        for vid in range(2):
            results = []
            for q in self.case["questions"]:
                r = {"run_id": f"run{vid}{q['question_id']}", "timestamp": "2026-09-20", "model": "qwen3.8-max",
                     "input_mode": "video", "thinking_effort": "default", "question_id": q["question_id"],
                     "question": q["text_en"], "raw_answer": "RAW_SECRET", "final_answer": "SECRET_NORMAL",
                     "judgment": {"verdict": "knowledge_trapped", "confidence": .99}}
                results.append(r)
            self.case["videos"].append({"video_id": f"v{vid}", "role": "conflict", "status": "ready",
                                        "local_path": "videos/seedance/test/sample.mp4", "qa_results": results})
        write_json(self.group / "case001.json", self.case)
        self.path_patch = patch.object(adapter, "media_path", return_value=self.media)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    def make_run(self, name="audit"):
        run = self.root / name
        prepare(run, self.dataset, self.config)
        return run

    def answer_all(self, audit, who="a"):
        for task in audit.tasks.values():
            if task["kind"] == "qa":
                audit.store.write(who, task["id"], "answer", {"answer": "My independent answer"})

    def test_default_groups_exclude_extra_experiments(self):
        for name in STANDARD_GROUPS:
            (self.dataset/name).mkdir()
        extra=self.dataset/"fairy_based_on_video"
        extra.mkdir()
        (extra/"invalid.json").write_text("must not be read", encoding="utf-8")
        self.config["groups"] = []
        units, _ = inventory(self.dataset, self.config)
        self.assertEqual(set(units), set(STANDARD_GROUPS))
        self.assertEqual(len(units), 4)

    def test_twenty_per_group_and_repeatability(self):
        units = [{"key": str(i)} for i in range(60)]
        a = draw(units, 20, 17, "qa", "g")
        b = draw(list(reversed(units)), 20, 17, "qa", "g")
        self.assertEqual(a, b)
        self.assertEqual(len({r["key"] for r in a}), 20)
        self.assertNotEqual(a, draw(units, 20, 17, "judge", "g"))
        self.assertEqual(len(draw(units[:7], 20, 17, "qa", "g")), 7)

    def test_prepare_freezes_samples_and_preserves_source(self):
        before = file_hash(self.group / "case001.json")
        first, second = self.make_run("one"), self.make_run("two")
        for name in ("qa_samples.jsonl", "judge_samples.jsonl"):
            self.assertEqual(read_jsonl(first/name), read_jsonl(second/name))
            self.assertEqual(len(read_jsonl(first/name)), 2)
        self.assertEqual(before, file_hash(self.group / "case001.json"))
        self.assertEqual(len(list((first/"media").iterdir())), 1)
        with self.assertRaises(ValueError):
            prepare(first, self.dataset, self.config)

    def test_independent_pages_only_require_answer(self):
        audit = Audit(self.make_run())
        qa = next(t for t in audit.tasks.values() if t["kind"] == "qa")
        judge = next(t for t in audit.tasks.values() if t["kind"] == "judge")
        self.assertTrue(all(t["kind"]=="qa" for t in audit.index("a","qa")["items"]))
        self.assertTrue(all(t["kind"]=="judge" for t in audit.index("a","judge")["items"]))
        public = json.dumps(audit.task(qa["id"], "a"))
        for secret in ("SECRET_NORMAL", "SECRET_CONFLICT", "RAW_SECRET", "case001"):
            self.assertNotIn(secret, public)
        independent=audit.task(judge["id"],"a")
        self.assertNotIn("raw_answer", independent)
        self.assertNotIn("qa_input", independent)
        self.assertFalse(independent["has_video"])
        self.assertEqual(independent["judge_input"], judge["judge_input"])
        self.assertNotIn("llm_judgment",independent)
        with self.assertRaises(ValueError):
            audit.media(judge["id"],"a")
        audit.store.write("a",judge["id"],"judge",{"answer":"knowledge_trapped"})
        self.assertNotIn("llm_judgment",audit.task(judge["id"],"a"))
        self.assertNotIn((qa["id"],"answer"),audit.store.state("a"))
        audit.store.write("a",qa["id"],"answer",{"answer":"draft"},draft=True)
        self.assertEqual(audit.task(qa["id"],"a")["draft"]["answer"],"draft")
        audit.store.write("a",qa["id"],"answer",{"answer":"My answer"})
        self.assertEqual(audit.task(qa["id"],"a")["submission"],{"answer":"My answer"})
        self.assertNotIn("references",audit.task(qa["id"],"a"))
        with self.assertRaises(ValueError):
            audit.store.write("a",qa["id"],"answer",{"answer":"overwrite"})
        with self.assertRaises(ValueError):
            audit.store.write("b",qa["id"],"classify",{"answer":"context_grounded"})
        with self.assertRaises(ValueError):
            audit.store.write("b",qa["id"],"answer",{"answer":"answer","reason":"extra field"})

    def test_missing_data_remains_in_samples_without_fake_answers(self):
        self.media.unlink()
        audit=Audit(self.make_run())
        qa=next(t for t in audit.tasks.values() if t["kind"]=="qa")
        self.assertTrue(qa["errors"])
        with self.assertRaises(ValueError):
            audit.store.write("a",qa["id"],"answer",{"answer":"guess"})
        self.assertEqual(len(read_jsonl(audit.run/"qa_samples.jsonl")),2)

    def test_variant_questions_and_stale_fingerprints(self):
        v = self.case["videos"][0]
        private = copy.deepcopy(self.case["questions"][0])
        private["text_en"] = "PRIVATE question"
        v["variant_context"] = {"questions": [private], "title": "Private title", "conflict_spec": self.case["conflict_spec"]}
        v["qa_results"] = [v["qa_results"][0]]
        v["qa_results"][0]["question"] = private["text_en"]
        v["qa_results"][0]["input_fingerprint"] = "stale"
        self.case["videos"] = [v]
        write_json(self.group/"case001.json", self.case)
        audit = Audit(self.make_run())
        tasks = list(audit.tasks.values())
        self.assertTrue(all(t["qa_input"]["question"] == "PRIVATE question" for t in tasks))
        judge = next(t for t in tasks if t["kind"] == "judge")
        self.assertIn("QA input fingerprint is stale", judge["errors"])
        self.assertEqual(audit.manifest["inventory"]["sample_group"]["qa_shortfall"], 1)

    def test_answer_only_metrics_do_not_guess_unscored_answers(self):
        audit=Audit(self.make_run())
        qa=[t for t in audit.tasks.values() if t["kind"]=="qa"]
        judge=[t for t in audit.tasks.values() if t["kind"]=="judge"]
        audit.store.write("a",qa[0]["id"],"answer",{"answer":qa[0]["references"]["normal"]})
        audit.store.write("a",qa[1]["id"],"answer",{"answer":"a paraphrase needing semantic scoring"})
        audit.store.write("a",judge[0]["id"],"judge",{"answer":"knowledge_trapped"})
        audit.store.write("a",judge[1]["id"],"judge",{"answer":"context_grounded"})
        state=audit.store.state("a")
        scores=scores_for(audit.store,"a")
        q=qa_stats(qa,state,scores)
        self.assertEqual(q["answered"],2)
        self.assertEqual(q["scored"],1)
        self.assertEqual(q["pending_scoring"],1)
        self.assertEqual(q["knowledge_trapped_rate"],1)
        j=judge_stats(judge,state)
        self.assertEqual(j["agreement"],.5)
        self.assertEqual(j["material_scope"],{"llm_judge_text_only":2})
        self.assertIsNone(judge_stats(judge,{})["agreement"])
        result=report(audit.run,"a")
        self.assertEqual(result["annotators"]["a"]["overall_judge"]["agreement"],.5)
        self.assertTrue((audit.run/"reports"/"a"/"qa_report.md").exists())
        self.assertTrue((audit.run/"reports"/"a"/"judge_report.md").exists())

    def test_http_media_ranges_and_post_token(self):
        audit = Audit(self.make_run())
        server = make_server(audit, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        tid = next(t["id"] for t in audit.tasks.values() if t["kind"] == "qa")
        try:
            with urlopen(base+"/") as response:
                self.assertIn("text/html", response.headers["Content-Type"])
            with urlopen(Request(base+f"/media/{tid}?annotator=a", headers={"Range": "bytes=10-19"})) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), bytes(range(10,20)))
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base+f"/media/{tid}?annotator=a", headers={"Range": "bytes=999-"}))
            self.assertEqual(error.exception.code, 416)
            body=json.dumps({"annotator":"a","task_id":tid,"stage":"answer","data":{"answer":"draft"}}).encode()
            with self.assertRaises(HTTPError):
                urlopen(Request(base+"/api/draft", data=body, headers={"Content-Type":"application/json"}))
            with urlopen(Request(base+"/api/draft", data=body, headers={"X-Audit-Token":audit.token})) as response:
                self.assertTrue(json.load(response)["ok"])
            with self.assertRaises(HTTPError):
                urlopen(base+"/tasks.jsonl")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_missing_conditions_and_latest_attempt_do_not_change_sample(self):
        self.config["per_group"] = 6
        v=self.case["videos"][0]
        extra=copy.deepcopy(v["qa_results"][0])
        extra["thinking_effort"]=None
        v["qa_results"].append(extra)
        latest=copy.deepcopy(v["qa_results"][0])
        latest.update(timestamp="2026-09-29",run_id="latest_without_judge",judgment=None)
        v["qa_results"].append(latest)
        write_json(self.group/"case001.json", self.case)
        run=self.make_run()
        samples=read_jsonl(run/"judge_samples.jsonl")
        tasks=[t for t in read_jsonl(run/"tasks.jsonl") if t["kind"]=="judge"]
        self.assertEqual(len(samples),6)
        self.assertEqual(len(tasks),6)
        self.assertEqual(sum(t["result"] is None for t in tasks),0)
        self.assertEqual(len({t["qa_key"] for t in tasks}),6)
        self.assertTrue(all(not t["errors"] for t in tasks))

    def test_named_progress_and_rename_preserve_history(self):
        run = self.make_run()
        audit = Audit(run)
        task = next(t for t in audit.tasks.values() if t["kind"] == "qa")
        store = audit.store
        store.write("old", task["id"], "answer", {"answer": "draft"}, draft=True)
        store.rename("old", "张三")
        self.assertEqual(store.draft("张三", task["id"], "answer")["answer"], "draft")
        self.assertEqual(store.draft("old", task["id"], "answer"), {})
        store.write("张三", task["id"], "answer", {"answer": "answer"})
        self.assertFalse(store.state("reviewer02"))
        store.write("reviewer02", task["id"], "answer", {"answer": "other"}, draft=True)
        with self.assertRaises(ValueError):
            store.rename("张三", "reviewer02")
        self.assertEqual(store.state("张三")[(task["id"], "answer")]["answer"], "answer")
        store.rename("张三", "reviewer01")
        self.assertFalse(store.state("张三"))
        self.assertTrue(Audit(run).store.state("reviewer01"))

    def test_stale_description_is_not_replayed_as_current(self):
        v=copy.deepcopy(self.case["videos"][0])
        v["seedance_prompt_en"]="changed prompt"
        v["description"]={"context_en":"old context","source_sha256":"old-hash"}
        self.assertTrue(adapter.description_errors(v,{"sha256":"pixels"}))

    def test_frozen_input_tampering_is_detected(self):
        run = self.make_run()
        (run/"tasks.jsonl").write_text("{}\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            Audit(run)


if __name__ == "__main__":
    unittest.main()
