import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcd_v1 import run_mcd_v1_batch as batch
from mcd_v1.run_mcd_v1 import cached_model
from vconflict_pipeline import core
from vconflict_pipeline.settings import COSMOS_QA_MODEL


class BatchTests(unittest.TestCase):
    def test_model_loaded_once_and_config_guarded(self):
        args = argparse.Namespace(model="model", revision=None, device="cpu", dtype="float32")
        processor, model, runtime = Mock(), Mock(), {}
        first = cached_model(args, "dtype", processor, model, runtime)
        self.assertEqual(first, cached_model(args, "dtype", processor, model, runtime))
        processor.from_pretrained.assert_called_once()
        model.from_pretrained.assert_called_once()
        args.device = "cuda:0"
        with self.assertRaises(ValueError):
            cached_model(args, "dtype", processor, model, runtime)

    def fixture(self, root):
        for module in (batch, core):
            patcher = patch.object(module, "PROJECT_ROOT", root)
            patcher.start()
            self.addCleanup(patcher.stop)
        videos = root / "videos/seedance"
        videos.mkdir(parents=True)
        cases = root / "cases"
        cases.mkdir()
        for n, verdict in enumerate(("knowledge_trapped", "context_grounded")):
            video = videos / f"v{n}.mp4"
            control = videos / f"c{n}.mp4"
            video.touch()
            control.touch()
            question = {"question_id": "q", "text_en": f"Question {n}?",
                        "conflict_video_reference_en": "SECRET_CONFLICT", "normal_control_reference_en": "SECRET_NORMAL"}
            record = {"model": COSMOS_QA_MODEL, "thinking_effort": None, "input_mode": "video",
                      "question_id": "q", "question": question["text_en"], "timestamp": "2026-01-01",
                      "final_answer": "old answer", "judgment": {"verdict": verdict}}
            case = {"case_id": f"case{n}", "questions": [question], "videos": [
                {"video_id": "v1", "role": "conflict", "status": "ready", "local_path": str(video.relative_to(batch.PROJECT_ROOT)), "qa_results": [record]},
                {"video_id": "control", "role": "control", "status": "ready", "local_path": str(control.relative_to(batch.PROJECT_ROOT))}]}
            (cases / f"{n}.json").write_text(json.dumps(case))
        return cases

    def test_selection_pairing_and_latest_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = self.fixture(root)
            manifest = batch.select_samples(cases, 1, 42)
            self.assertEqual(manifest, batch.select_samples(cases, 1, 42))
            self.assertEqual(len(manifest["items"]), 4)
            for conflict in manifest["items"][:2]:
                control = next(x for x in manifest["items"] if x["id"] == conflict["control_id"])
                self.assertEqual(conflict["question"], control["question"])
                self.assertEqual(conflict["pairs"], control["pairs"])
            path = cases / "0.json"
            case = batch.read_json(path)
            old = case["videos"][0]["qa_results"][0]
            case["videos"][0]["qa_results"].append({**old, "timestamp": "2026-02-01", "judgment": {"verdict": "ambiguous_or_unjudgeable"}})
            path.write_text(json.dumps(case))
            with self.assertRaises(ValueError):
                batch.select_samples(cases, 1, 42)

    def test_batch_resume_and_no_reference_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = self.fixture(root)
            output = root / "results"
            argv = ["--case-dir", str(cases), "--per-group", "1", "--output-dir", str(output)]
            runtimes = []
            def fake_run(command, runtime):
                self.assertNotIn("SECRET", " ".join(command))
                runtimes.append(runtime)
                target = Path(command[command.index("--output") + 1])
                batch.write_json(target, {"runs": {name: {"status": "ok", "final_answer": "answer"}
                                                  for name in ("baseline", "mcd_v1")}})
                return 0
            with patch.object(batch, "run_one", side_effect=fake_run) as run:
                self.assertEqual(batch.main(argv + ["--prepare-only"]), 0)
                run.assert_not_called()
                self.assertEqual(batch.main(argv), 0)
                self.assertEqual(run.call_count, 4)
                self.assertTrue(all(x is runtimes[0] for x in runtimes))
                self.assertEqual(batch.main(argv), 0)
                self.assertEqual(run.call_count, 4)
                with self.assertRaises(SystemExit):
                    batch.main(argv + ["--lambda", "0.8"])
                fingerprints = batch.code_fingerprints()
                fingerprints["vconflict_pipeline/qa.py"] = "changed prompt code"
                with patch.object(batch, "code_fingerprints", return_value=fingerprints):
                    with self.assertRaises(SystemExit):
                        batch.main(argv)
                self.assertEqual(run.call_count, 4)
            self.assertEqual(len(batch.read_json(output / "report.json")), 4)

    def test_partial_result_is_not_success(self):
        self.assertFalse(batch.successful({"runs": {"baseline": {"status": "ok"}}}))
        self.assertFalse(batch.successful({"runs": {"baseline": {"status": "ok"}, "mcd_v1": {"status": "truncated"}}}))

    def test_lambda_zero_mismatch_is_failed_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            cases = self.fixture(output)
            manifest = batch.select_samples(cases, 1)
            item = manifest["items"][0]
            batch.write_json(output / (item["id"] + ".json"), {
                "lambda_zero_matches": False,
                "runs": {name: {"status": "ok"} for name in ("baseline", "mcd_v1")},
            })
            self.assertEqual(batch.report(manifest, output)[0]["status"], "failed")

    def test_existing_results_without_config_are_not_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = self.fixture(root)
            output = root / "results"
            argv = ["--case-dir", str(cases), "--per-group", "1", "--output-dir", str(output)]
            batch.main(argv + ["--prepare-only"])
            manifest = batch.read_json(output / "manifest.json")
            target = output / (manifest["items"][0]["id"] + ".json")
            batch.write_json(target, {"runs": {}})
            original = target.read_bytes()
            with patch.object(batch, "run_one") as run:
                with self.assertRaises(SystemExit):
                    batch.main(argv)
                run.assert_not_called()
            self.assertFalse((output / "config.json").exists())
            self.assertEqual(target.read_bytes(), original)

    def test_atomic_json_never_publishes_partial_or_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "result.json"
            with patch("mcd_v1.storage.json.dump", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    batch.write_json(target, {"partial": True})
            self.assertEqual(list(root.iterdir()), [])
            batch.write_json(target, {"original": True})
            original = target.read_bytes()
            with self.assertRaises(FileExistsError):
                batch.write_json(target, {"replacement": True})
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(root.iterdir()), [target])

    def test_based_history_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = self.fixture(Path(tmp))
            path = cases / "0.json"
            case = batch.read_json(path)
            case["videos"][0]["qa_results"][0]["based"] = True
            path.write_text(json.dumps(case))
            with self.assertRaisesRegex(ValueError, "Not enough eligible knowledge_trapped"):
                batch.select_samples(cases, 1)

    def test_controls_are_deduplicated_for_identical_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = self.fixture(Path(tmp))
            for path in cases.glob("*.json"):
                case = batch.read_json(path)
                case["videos"].insert(1, {**case["videos"][0], "video_id": "v2"})
                path.write_text(json.dumps(case))
            manifest = batch.select_samples(cases, 2)
            controls = [i for i in manifest["items"] if i["role"] == "control"]
            self.assertEqual(len(manifest["items"]), 6)
            self.assertEqual(len(controls), 2)
            self.assertTrue(all(len(i["pairs"]) == 2 for i in controls))


if __name__ == "__main__":
    unittest.main()
