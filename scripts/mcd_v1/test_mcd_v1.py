"""CPU checks: python scripts/mcd_v1/test_mcd_v1.py."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcd_v1.decoding import TextPriorContrastiveProcessor, contrastive_scores
from mcd_v1.run_mcd_v1 import messages_for, parse_mcd_answer


class FakeModel:
    def __init__(self, fail=False):
        self.model = SimpleNamespace(rope_deltas=torch.tensor([[17]]))
        self.calls = []
        self.fail = fail

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.model.rope_deltas is not None:
            raise AssertionError("Text branch inherited the video's RoPE state")
        self.model.rope_deltas = torch.tensor([[999]])
        if self.fail:
            raise RuntimeError("simulated failure")
        return SimpleNamespace(logits=torch.tensor([[[2.0, 0.0, -1.0]]]))


class MCDV1Tests(unittest.TestCase):
    def test_exact_formula_not_gamma_formula(self):
        video = torch.log(torch.tensor([[0.6, 0.3, 0.1]]))
        text = torch.log(torch.tensor([[0.90, 0.02, 0.08]]))
        scores = contrastive_scores(video, text, weight=0.5, beta=0)
        expected = torch.log_softmax(video, -1) - 0.5 * torch.log_softmax(text, -1)
        torch.testing.assert_close(scores, expected)
        self.assertEqual(scores.argmax(-1).item(), 1)
        self.assertEqual(video.argmax(-1).item(), 0)

    def test_plausibility_cutoff_blocks_extreme_negative_prior(self):
        video = torch.log(torch.tensor([[0.80, 0.19, 0.01]]))
        text = torch.log(torch.tensor([[0.5, 0.499999, 0.000001]]))
        unmasked = contrastive_scores(video, text, weight=1, beta=0)
        masked = contrastive_scores(video, text, weight=1, beta=0.1)
        self.assertEqual(unmasked.argmax(-1).item(), 2)
        self.assertTrue(torch.isneginf(masked[0, 2]))
        self.assertFalse(torch.isneginf(masked[0, video.argmax(-1).item()]))

    def processor(self, model, weight=0.5):
        return TextPriorContrastiveProcessor(model, {
            "input_ids": torch.tensor([[8, 9]]),
            "attention_mask": torch.ones((1, 2), dtype=torch.long),
            "mm_token_type_ids": torch.zeros((1, 2), dtype=torch.long),
        }, video_prompt_length=3, weight=weight)

    def test_shared_history_and_rope_restoration(self):
        model = FakeModel()
        original_rope = model.model.rope_deltas
        proc = self.processor(model)
        for history in ([], [1], [1, 2]):
            proc(torch.tensor([[4, 5, 6] + history]), torch.tensor([[2.0, 1.0, 0.0]]))
            call = model.calls[-1]
            self.assertEqual(call["input_ids"].tolist(), [[8, 9] + history])
            self.assertEqual(call["attention_mask"].shape, call["input_ids"].shape)
            self.assertEqual(call["mm_token_type_ids"].count_nonzero().item(), 0)
            self.assertFalse(call["use_cache"])
            self.assertNotIn("pixel_values_videos", call)
            self.assertIs(model.model.rope_deltas, original_rope)

    def test_rope_restored_on_failure(self):
        model = FakeModel(fail=True)
        original_rope = model.model.rope_deltas
        with self.assertRaisesRegex(RuntimeError, "simulated"):
            self.processor(model)(torch.tensor([[4, 5, 6]]), torch.zeros((1, 3)))
        self.assertIs(model.model.rope_deltas, original_rope)

    def test_zero_lambda_is_exact_identity_and_skips_text(self):
        model = FakeModel(fail=True)
        scores = torch.tensor([[3.0, 3.0, -1.0]])
        result = self.processor(model, weight=0)(torch.tensor([[4, 5, 6]]), scores)
        self.assertIs(result, scores)
        self.assertEqual(model.calls, [])

    def test_invalid_parameters_and_logits_fail_explicitly(self):
        logits = torch.zeros((1, 3))
        for weight, beta in ((-1, 0.1), (float("nan"), 0.1), (0.5, -0.1), (0.5, 1.1)):
            with self.assertRaises(ValueError):
                contrastive_scores(logits, logits, weight=weight, beta=beta)
        with self.assertRaises(ValueError):
            contrastive_scores(torch.tensor([[float("nan")]]), None, weight=0)

    def test_text_conditions_identical_except_video(self):
        video_messages = messages_for("same question", "/example.mp4")
        text_messages = messages_for("same question")
        self.assertEqual(video_messages[0], text_messages[0])
        self.assertEqual(video_messages[1]["content"][1:], text_messages[1]["content"])


    def test_inline_final_answer_recovered_with_warning(self):
        result = parse_mcd_answer("The strip changed color. Final answer: Blue.  ", "eos")
        self.assertEqual(result["final_answer"], "Blue.")
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["parse_error"])
        self.assertIsNotNone(result["format_warning"])

    def test_standard_answer_unchanged(self):
        result = parse_mcd_answer("<think></think>\nExplanation.\nFinal answer: Blue.\n", "eos")
        self.assertEqual(result["final_answer"], "Blue.")
        self.assertIsNone(result["format_warning"])

    def test_invalid_final_answers_still_fail(self):
        examples = ["", "Explanation. Final answer:   ",
                    "Explanation. Final answer: Blue.\nMore explanation.",
                    "<think>Final answer: Blue.</think>",
                    "<think>Final answer: Blue.",
                    "Example Final answer: Red. Actual Final answer: Blue."]
        for raw in examples:
            with self.subTest(raw=raw):
                result = parse_mcd_answer(raw, "eos")
                self.assertEqual(result["status"], "parse_error")
                self.assertIsNone(result["final_answer"])

    def test_missing_marker_requires_manual_evaluation(self):
        result = parse_mcd_answer("<think>private reasoning</think> Blue.", "eos")
        self.assertEqual(result["status"], "format_fallback")
        self.assertEqual(result["evaluation_answer"], "Blue.")
        self.assertIsNone(result["final_answer"])
        self.assertTrue(result["requires_manual_review"])
        self.assertIsNotNone(result["parse_error"])

    def test_missing_marker_truncated_is_not_fallback(self):
        result = parse_mcd_answer("The ball falls", "length")
        self.assertEqual(result["status"], "truncated")
        self.assertIsNone(result["evaluation_answer"])

    def test_fallback_report_is_not_standard_success(self):
        from mcd_v1.run_mcd_v1_batch import result_status, successful
        result = {"runs": {"baseline": {"status": "ok"},
                           "mcd_v1": {"status": "format_fallback"}}}
        self.assertEqual(result_status(result), "format_fallback")
        self.assertFalse(successful(result))

    def test_reasoning_marker_ignored(self):
        result = parse_mcd_answer("<think>Final answer: Red.</think> Saw blue. Final answer: Blue.", "eos")
        self.assertEqual(result["final_answer"], "Blue.")

    def test_truncation_not_hidden_by_recovery(self):
        result = parse_mcd_answer("Explanation. Final answer: Blue.", "length")
        self.assertEqual(result["status"], "truncated")
        self.assertIsNotNone(result["format_warning"])



if __name__ == "__main__":
    unittest.main()
