"""Offline checks for question-stage failure isolation in the 25-video batch."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "math_batch_under_test", ROOT / "artifacts/math_expansion_20260923/run_batch.py"
)
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


class BatchFailureTests(unittest.TestCase):
    def test_failed_question_variant_does_not_block_later_variants(self):
        rows = [{"label": label, "case_id": label.lower()} for label in ("M07", "M08", "M09")]
        calls = []
        completed = set()
        def pipeline(args):
            cid = args[args.index("--case-id") + 1]
            calls.append(cid)
            if cid == "m08":
                raise RuntimeError("question audit failed")
            completed.add(cid)
        with tempfile.TemporaryDirectory() as temp:
            existing = Path(temp) / "exists.json"
            existing.touch()
            with patch.object(batch, "HERE", Path(temp)), \
                    patch.object(batch, "prepare", return_value=rows), \
                    patch.object(batch, "runtime_path", return_value=existing), \
                    patch.object(batch, "checked_case", side_effect=lambda r: {"questions": [1] if r["case_id"] in completed else []}), \
                    patch.object(batch, "pipeline", side_effect=pipeline), \
                    patch.object(sys, "argv", ["batch", "questions"]):
                with self.assertRaisesRegex(RuntimeError, "Questions failed for: M08"):
                    batch.main()
        self.assertEqual(calls, ["m07", "m08", "m09"])
        self.assertEqual(completed, {"m07", "m09"})

    def test_generation_preflight_blocks_any_missing_questions(self):
        rows = [{"label": label, "case_id": label.lower()} for label in ("M07", "M08", "M09")]
        with tempfile.TemporaryDirectory() as temp:
            existing = Path(temp) / "exists.json"
            existing.touch()
            with patch.object(batch, "HERE", Path(temp)), \
                    patch.object(batch, "prepare", return_value=rows), \
                    patch.object(batch, "runtime_path", return_value=existing), \
                    patch.object(batch, "checked_case", side_effect=lambda r: {"questions": [] if r["label"] == "M08" else [1]}), \
                    patch.object(batch, "pipeline") as pipeline, \
                    patch.object(sys, "argv", ["batch", "generate"]):
                with self.assertRaisesRegex(RuntimeError, "Run questions first: M08"):
                    batch.main()
                pipeline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
