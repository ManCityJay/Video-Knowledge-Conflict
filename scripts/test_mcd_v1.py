"""Small CPU checks to run on Chenmd: python scripts/test_mcd_v1.py"""

import unittest
from types import SimpleNamespace

import torch

from vconflict_pipeline.mcd_v1 import TextPriorContrastiveProcessor, contrastive_scores
from run_mcd_v1 import messages_for


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


if __name__ == "__main__":
    unittest.main()
