"""Offline regression tests; never call a model or write the live dataset."""
import argparse
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from vconflict_pipeline import authoring as a
from vconflict_pipeline.cli import build_parser, _validate
from vconflict_pipeline.core import validate_case


def question(text="Starting with [1, 2], append 3 to the end. What is the final list?"):
    return {"question_en": text, "conflict_video_reference_en": "The list is [3, 1, 2].",
            "normal_control_reference_en": "The list is [1, 2, 3]."}


def audit(ok=True):
    return {"checks": [{"index": 1, "self_contained": ok,
                        "answer_en": "[1, 2, 3]" if ok else "",
                        "derivation_en": "Append 3 after the existing two items." if ok else "",
                        "issues": [] if ok else ["Missing initial list and appended value."]}]}


class BlindValidationTests(unittest.TestCase):
    def verify(self, q, api, repairs=2, preserve=False, math=True):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(a, "PROJECT_ROOT", Path(tmp)), \
                patch.object(a, "openrouter_json", side_effect=api):
            return a.verify_authored_questions(
                q, case_context={"private": "HIDDEN_DESIGN"},
                system_prompt=a.MATHEMATICS_ALGORITHM_QUESTION_VERIFY_SYSTEM_PROMPT,
                api_key="offline", timeout=1, max_repairs=repairs, max_retries=0,
                request_limiter=None, require_self_contained=math, preserve_count=preserve,
            )

    def test_blind_request_has_no_design_references_or_history(self):
        seen = []
        def api(**kw):
            seen.append(kw)
            data = json.loads(kw["messages"][1]["content"])
            if kw["schema_name"] == "math_question_only_audit":
                self.assertEqual(data, {"questions": [question()["question_en"]]})
                self.assertEqual(len(kw["messages"]), 2)
                self.assertNotIn("HIDDEN_DESIGN", str(kw["messages"]))
                self.assertNotIn("[3, 1, 2]", str(kw["messages"]))
                return audit(), {}
            self.assertEqual(data["question_only_audit"], audit())
            return {"valid": True, "issues": [], "questions": data["questions"]}, {}
        self.assertEqual(self.verify([question()], api), [question()])
        self.assertEqual(len(seen), 2)

    def test_prior_cue_draft_reaches_repair_then_fresh_blind_and_frozen_checks(self):
        original = question("Starting with [1, 2], append 3. What should the final list be?")
        calls = []
        def api(**kw):
            calls.append(kw["schema_name"])
            data = json.loads(kw["messages"][1]["content"])
            if kw["schema_name"] == "math_question_only_audit":
                self.assertEqual(data, {"questions": [question()["question_en"]]})
                return audit(), {}
            if data.get("validation_mode") != "check_only":
                self.assertIn("explicit prior cue", str(data["previous_issues"]))
                self.assertNotIn("question_only_audit", data)
            else:
                self.assertEqual(data["question_only_audit"], audit())
            return {"valid": True, "issues": [], "questions": [question()]}, {}
        self.assertEqual(self.verify([original], api, repairs=0), [question()])
        self.assertEqual(calls, ["knowledge_conflict_question_validation", "math_question_only_audit",
                                 "knowledge_conflict_question_validation"])

    def test_unrepaired_prior_cue_cannot_be_saved(self):
        original = question("Starting with [1, 2], append 3. What should the final list be?")
        def api(**kw):
            self.assertEqual(kw["schema_name"], "knowledge_conflict_question_validation")
            return {"valid": True, "issues": [], "questions": [original]}, {}
        with self.assertRaisesRegex(a.PipelineError, "explicit prior cue"):
            self.verify([original], api, repairs=0)

    def test_local_reference_repair_with_unchanged_text_still_gets_blind_audit(self):
        original = question()
        original["conflict_video_reference_en"] = original["normal_control_reference_en"]
        calls = []
        def api(**kw):
            calls.append(kw["schema_name"])
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            return {"valid": True, "issues": [], "questions": [question()]}, {}
        self.assertEqual(self.verify([original], api, repairs=0), [question()])
        self.assertEqual(calls, ["knowledge_conflict_question_validation", "math_question_only_audit",
                                 "knowledge_conflict_question_validation"])

    def test_context_validator_cannot_override_failed_blind_check(self):
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(False), {}
            data = json.loads(kw["messages"][1]["content"])
            return {"valid": True, "issues": [], "questions": data["questions"]}, {}
        with self.assertRaises(a.PipelineError):
            self.verify([question("What is the final list?")], api, repairs=0)

    def test_repaired_candidate_requires_fresh_blind_check(self):
        requests = []
        def api(**kw):
            requests.append(kw["schema_name"])
            data = json.loads(kw["messages"][1]["content"])
            if kw["schema_name"] == "math_question_only_audit":
                return audit(data["questions"] == [question()["question_en"]]), {}
            return {"valid": True, "issues": [], "questions": [question()]}, {}
        self.assertEqual(self.verify([question("What is the final list?")], api), [question()])
        self.assertEqual(requests, ["math_question_only_audit", "knowledge_conflict_question_validation"] * 2)

    def test_last_repair_gets_fresh_audit_and_frozen_final_check(self):
        modes = []
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            data = json.loads(kw["messages"][1]["content"])
            modes.append(data.get("validation_mode", "repair"))
            if data.get("validation_mode") == "check_only":
                self.assertIn("FINAL CHECK-ONLY", kw["messages"][0]["content"])
                return {"valid": True, "issues": [], "questions": data["questions"]}, {}
            return {"valid": True, "issues": [], "questions": [question("Another question?")]}, {}
        self.assertEqual(self.verify([question()], api, repairs=0), [question("Another question?")])
        self.assertEqual(modes, ["repair", "check_only"])

    def test_final_check_cannot_keep_rewriting_question(self):
        calls = []
        def api(**kw):
            calls.append(kw["schema_name"])
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            data = json.loads(kw["messages"][1]["content"])
            text = "Another question?" if data.get("validation_mode") != "check_only" else "Yet another question?"
            return {"valid": True, "issues": [], "questions": [question(text)]}, {}
        with self.assertRaisesRegex(a.PipelineError, "edited the frozen"):
            self.verify([question()], api, repairs=0)
        self.assertEqual(len(calls), 4)

    def test_repair_marked_invalid_due_to_stale_audit_gets_final_check(self):
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            data = json.loads(kw["messages"][1]["content"])
            if data.get("validation_mode") == "check_only":
                return {"valid": True, "issues": [], "questions": data["questions"]}, {}
            return {"valid": False, "issues": ["Repaired question needs a fresh audit."],
                    "questions": [question("Repaired question?")]}, {}
        self.assertEqual(self.verify([question()], api, repairs=0), [question("Repaired question?")])

    def test_last_repair_failing_fresh_audit_reports_specific_issue(self):
        audit_calls = []
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                audit_calls.append(kw)
                return audit(len(audit_calls) == 1), {}
            return {"valid": True, "issues": [], "questions": [question("Missing data?")]}, {}
        with self.assertRaisesRegex(a.PipelineError, "Missing initial list and appended value"):
            self.verify([question()], api, repairs=0)
        self.assertEqual(len(audit_calls), 2)

    def test_final_check_must_validate_normal_reference_against_fresh_audit(self):
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            data = json.loads(kw["messages"][1]["content"])
            if data.get("validation_mode") == "check_only":
                self.assertEqual(data["question_only_audit"], audit())
                return {"valid": False, "issues": ["Normal reference differs from fresh audit."],
                        "questions": data["questions"]}, {}
            return {"valid": True, "issues": [], "questions": [question("Repaired text?")]}, {}
        with self.assertRaisesRegex(a.PipelineError, "differs from fresh audit"):
            self.verify([question()], api, repairs=0)

    def test_failed_validation_saves_question_audit_and_validator_outputs(self):
        saved = []
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(False), {}
            data = json.loads(kw["messages"][1]["content"])
            return {"valid": False, "issues": ["Missing premise."], "questions": data["questions"]}, {}
        with patch.object(a, "atomic_write_json", side_effect=lambda p,d: saved.append((p, copy.deepcopy(d)))):
            with self.assertRaisesRegex(a.PipelineError, "Diagnostic:"):
                self.verify([question()], api, repairs=0)
        self.assertEqual(len(saved), 1)
        trace = saved[0][1]
        self.assertEqual(trace["initial_questions"], [question()])
        self.assertEqual(trace["attempts"][0]["question_only_audit"], audit(False))
        self.assertFalse(trace["attempts"][0]["context_validation"]["valid"])
        self.assertNotIn("api_key", trace)

    def test_reference_only_repair_reuses_successful_text_audit(self):
        original = question()
        original["conflict_video_reference_en"] = "The reference cannot be repaired."
        calls = []
        def api(**kw):
            calls.append(kw["schema_name"])
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            return {"valid": True, "issues": [], "questions": [question()]}, {}
        self.assertEqual(self.verify([original], api, repairs=0), [question()])
        self.assertEqual(calls, ["math_question_only_audit", "knowledge_conflict_question_validation"])

    def test_reference_only_repair_still_requires_successful_blind_audit(self):
        original = question()
        original["conflict_video_reference_en"] = "The reference cannot be repaired."
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(False), {}
            return {"valid": True, "issues": [], "questions": [question()]}, {}
        with self.assertRaises(a.PipelineError):
            self.verify([original], api, repairs=0)

    def test_reference_only_repair_still_requires_valid_context_verdict(self):
        original = question()
        original["normal_control_reference_en"] = "The list is [1, 3, 2]."
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            return {"valid": False, "issues": ["Normal reference differs from blind answer."],
                    "questions": [question()]}, {}
        with self.assertRaisesRegex(a.PipelineError, "Normal reference"):
            self.verify([original], api, repairs=0)

    def test_reference_mismatch_rejected_by_context_verifier(self):
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            data = json.loads(kw["messages"][1]["content"])
            return {"valid": False, "issues": ["Normal reference differs from blind answer."],
                    "questions": data["questions"]}, {}
        with self.assertRaisesRegex(a.PipelineError, "Normal reference"):
            self.verify([question()], api, repairs=0)

    def test_missing_audit_entries_fail_closed(self):
        with self.assertRaisesRegex(a.PipelineError, "Malformed"):
            self.verify([question()], lambda **kw: ({"checks": []}, {}))

    def test_repair_cannot_change_question_count(self):
        def api(**kw):
            if kw["schema_name"] == "math_question_only_audit":
                return audit(), {}
            return {"valid": True, "issues": [], "questions": []}, {}
        with self.assertRaisesRegex(a.PipelineError, "exactly 1"):
            self.verify([question()], api, repairs=0, preserve=True)

    def test_non_math_uses_existing_validation_path(self):
        def api(**kw):
            self.assertEqual(kw["schema_name"], "knowledge_conflict_question_validation")
            return {"valid": True, "issues": [], "questions": [question()]}, {}
        self.assertEqual(self.verify([question()], api, math=False), [question()])


class ScopeRepairTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "dataset/cases/mathematics_algorithm_conflicts/append_inserts_at_front.json"
        self.case = json.loads(self.path.read_text())
        self.case["videos"] = [v for v in self.case["videos"] if v["video_id"] in {"v001", "v002", "v003", "control"}]
        for v in self.case["videos"]:
            v["qa_results"] = [{"marker": v["video_id"]}]
        self.args = argparse.Namespace(
            group=a.MATHEMATICS_ALGORITHM_GROUP, repair_variant_context=True,
            force=False, dataset_dir=ROOT / "dataset/cases", case_id=[self.case["case_id"]],
            case_workers=1, timeout=1, max_retries=0, max_repairs=2,
        )
        self.writes = []
        self.verified = []

    def video(self, case, vid):
        return next(v for v in case["videos"] if v["video_id"] == vid)

    def run_command(self, fail_at=None, unchanged=False):
        def verify(q, **kw):
            self.verified.append(kw)
            if len(self.verified) == fail_at:
                raise a.PipelineError("failed blind audit")
            return q if unchanged else [question() for _ in q]
        def validate(c):
            c = copy.deepcopy(c)
            for v in c["videos"]:
                v["qa_results"] = []
            validate_case(c)
        def api(**kw):
            return {"questions": [question()]}, {"id": "offline"}
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(a, "PROJECT_ROOT", Path(tmp)), \
                patch.object(a, "require_openrouter_api_key", return_value="offline"), \
                patch.object(a, "make_openrouter_limiter", return_value=None), \
                patch.object(a, "iter_case_paths", return_value=[self.path]), \
                patch.object(a, "load_case", return_value=copy.deepcopy(self.case)), \
                patch.object(a, "openrouter_json", side_effect=api) as model, \
                patch.object(a, "verify_authored_questions", side_effect=verify), \
                patch.object(a, "validate_case", side_effect=validate), \
                patch.object(a, "atomic_write_json", side_effect=lambda p,c: self.writes.append((p, copy.deepcopy(c)))):
            result = a.command_questions(self.args)
            if self.args.repair_variant_context:
                model.assert_not_called()
            return result

    def test_repair_only_variants_preserves_ids_and_backs_up_original(self):
        self.assertEqual(self.run_command(), 0)
        self.assertEqual(len(self.verified), 2)
        self.assertEqual(len(self.writes), 2)
        backup, saved = self.writes
        self.assertIn("backups", backup[0].parts)
        self.assertEqual(backup[1], self.case)
        self.assertEqual(saved[0], self.path)
        self.assertEqual(saved[1]["questions"], self.case["questions"])
        for vid in ["v001", "control"]:
            self.assertEqual(self.video(saved[1], vid), self.video(self.case, vid))
        for vid in ["v002", "v003"]:
            old = self.video(self.case, vid)
            new = self.video(saved[1], vid)
            self.assertEqual(new["qa_results"], [])
            self.assertEqual(new["variant_context"]["questions"][0]["question_id"],
                             old["variant_context"]["questions"][0]["question_id"])
            self.assertEqual(new["seedance_prompt_en"], old["seedance_prompt_en"])
            self.assertEqual(new["variant_context"]["conflict_spec"], old["variant_context"]["conflict_spec"])
        self.assertTrue(all(k["require_self_contained"] and k["preserve_count"] for k in self.verified))

    def test_variant_failure_does_not_save_or_clear_anything(self):
        self.assertEqual(self.run_command(fail_at=2), 1)
        self.assertEqual(self.writes, [])

    def test_unchanged_questions_keep_qa_and_do_not_write(self):
        self.assertEqual(self.run_command(unchanged=True), 0)
        self.assertEqual(self.writes, [])

    def test_future_missing_variant_automatically_uses_blind_gate(self):
        self.args.repair_variant_context = False
        self.video(self.case, "v003")["variant_context"]["questions"] = []
        self.assertEqual(self.run_command(), 0)
        self.assertEqual(len(self.verified), 1)
        self.assertTrue(self.verified[0]["require_self_contained"])
        self.assertEqual(self.verified[0]["case_context"]["question_scope"], "v003")
        self.assertEqual(len(self.writes), 1)

    def test_matching_control_comes_from_variant_not_parent(self):
        c = json.loads((self.path.parent / "bubble_sort_swaps_nonadjacent_elements.json").read_text())
        v = self.video(c, "v002")
        context = a.question_case_context(c, v)
        self.assertEqual(context["videos"], [{"role": "conflict", "seedance_prompt_en": v["seedance_prompt_en"]}])
        self.assertIn("[4, 3, 2, 1]", context["matched_control_prompts"][0])
        self.assertNotIn(self.video(c, "control")["seedance_prompt_en"], context["matched_control_prompts"])
        v["seedance_prompt_en"] += " Changed design."
        self.assertNotIn("matched_control_prompts", a.question_case_context(c, v))


class CliTests(unittest.TestCase):
    def test_repair_flag(self):
        parser = build_parser()
        args = parser.parse_args(["questions", "--group", a.MATHEMATICS_ALGORITHM_GROUP,
                                  "--repair-variant-context"])
        _validate(args, parser)
        self.assertTrue(args.repair_variant_context)
        args.group = "real_world_commonsense_conflicts"
        with self.assertRaises(SystemExit):
            _validate(args, parser)
        args.group = a.MATHEMATICS_ALGORITHM_GROUP
        args.force = True
        with self.assertRaises(SystemExit):
            _validate(args, parser)


if __name__ == "__main__":
    unittest.main(verbosity=2)
