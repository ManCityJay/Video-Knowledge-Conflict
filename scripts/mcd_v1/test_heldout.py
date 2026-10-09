import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcd_v1.prepare_heldout import build_manifest
from mcd_v1 import run_lambda_sweep as sweep
from mcd_v1.storage import write_json


class HeldoutTests(unittest.TestCase):
    def test_case_exclusion_video_units_control_dedup_and_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = root / "cases"
            cases.mkdir()
            for name in ("a.mp4", "b.mp4", "c.mp4"):
                (root / name).touch()
            case = {"case_id": "new", "questions": [{"question_id": "q", "text_en": "Q?",
                    "conflict_video_reference_en": "C", "normal_control_reference_en": "N"}],
                    "videos": [{"video_id": "a", "role": "conflict", "status": "ready", "local_path": "a.mp4"},
                               {"video_id": "b", "role": "conflict", "status": "ready", "local_path": "b.mp4"},
                               {"video_id": "c", "role": "control", "status": "ready", "local_path": "c.mp4"}]}
            write_json(cases / "new.json", case)
            write_json(cases / "old.json", {**case, "case_id": "pilot"})
            m = build_manifest(cases, {"items": [{"case_id": "pilot"}]}, root)
            self.assertEqual(m["counts"]["conflict_questions"], 2)
            self.assertEqual(m["counts"]["unique_control_questions"], 1)
            self.assertEqual(len(m["items"][-1]["pairs"]), 2)
            self.assertEqual({i["case_id"] for i in m["items"]}, {"new"})

    def test_three_lambda_sweep(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "v.mp4"
            video.touch()
            source = root / "manifest.json"
            write_json(source, {"items": [{"id": "x", "video": str(video), "question": "Q?",
                       "role": "conflict", "reference": "SECRET"}]})
            args = ["--manifest", str(source), "--output-dir", str(root / "out"),
                    "--model", "mock", "--lambdas", "0", "0.2", "0.3"]
            weights = []
            def fake(command, runtime):
                self.assertNotIn("SECRET", " ".join(command))
                weights.append(float(command[command.index("--lambda") + 1]))
                write_json(Path(command[command.index("--output") + 1]),
                           {"runs": {"mcd_v1": {"status": "ok"}}})
            with patch.object(sweep, "run_one", side_effect=fake):
                self.assertEqual(sweep.main(args), 0)
                self.assertEqual(sweep.main(args), 0)
            self.assertEqual(weights, [0, 0.2, 0.3])
            self.assertEqual(set(json.loads((root/"out/summary.json").read_text())), {"0.0", "0.2", "0.3"})


if __name__ == "__main__":
    unittest.main()
