import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcd_v1 import run_lambda_sweep as sweep
from mcd_v1.storage import write_json


class SweepTests(unittest.TestCase):
    def test_shared_baseline_resume_and_config_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "video.mp4"
            video.touch()
            manifest = root / "manifest.json"
            write_json(manifest, {"items": [{"id": "x", "video": str(video),
                       "question": "What happens?", "role": "conflict", "reference": "SECRET"}]})
            output = root / "out"
            args = ["--manifest", str(manifest), "--output-dir", str(output), "--model", "mock"]
            calls, runtimes = [], []
            def fake(command, runtime):
                self.assertNotIn("--compare-baseline", command)
                self.assertNotIn("SECRET", " ".join(command))
                self.assertEqual(command[command.index("--max-new-tokens") + 1], "512")
                weight = command[command.index("--lambda") + 1]
                calls.append(float(weight))
                runtimes.append(runtime)
                result = {"runs": {"mcd_v1": {"status": "format_fallback" if weight == "0.1" else "ok",
                          "evaluation_answer": "A", "seconds": 1}}}
                write_json(Path(command[command.index("--output") + 1]), result)
                return 0
            with patch.object(sweep, "run_one", side_effect=fake) as runner:
                self.assertEqual(sweep.main(args + ["--prepare-only"]), 0)
                runner.assert_not_called()
                self.assertEqual(sweep.main(args), 0)
                self.assertEqual(calls, list(sweep.WEIGHTS))
                self.assertTrue(all(r is runtimes[0] for r in runtimes))
                self.assertEqual(sweep.main(args), 0)
                self.assertEqual(len(calls), 5)
                with self.assertRaises(SystemExit):
                    sweep.main(args + ["--beta", "0.2"])
            rows = json.loads((output / "report.json").read_text())
            self.assertEqual(len(rows), 5)
            self.assertEqual(rows[1]["status"], "format_fallback")
            self.assertTrue(all(r["baseline_file"].endswith("lambda_0/x.json") for r in rows))


if __name__ == "__main__":
    unittest.main()
