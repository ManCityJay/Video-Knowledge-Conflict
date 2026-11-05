"""Serial local QA with isolated CD branches and one assistant continuation."""
from __future__ import annotations

import time

from vconflict_pipeline.qa import (
    FINAL_ANSWER_CONTINUATION_MAX_TOKENS, FINAL_ANSWER_PREFIX,
    MissingFinalAnswerError, extract_final_answer,
)
from cd.contrastive_common.adapters import Branch, eos_ids
from cd.contrastive_common.control import ReasoningControl, suppressed_tokens
from cd.contrastive_common.core import combine_logits
from cd.contrastive_common.generation import check_context, parsed
from cd.contrastive_common.video import load_frames
from .method import prepare


def decode(model, processor, video, question, *, family, alpha, beta,
           max_new_tokens, thinking_token_budget, stop, device, dtype, thinking=True,
           continuation=False):
    import torch
    generated = []
    controller = (ReasoningControl(processor.tokenizer, video['input_ids'][0].tolist(),
                                   family=family, budget=thinking_token_budget) if thinking else None)
    suppressed = suppressed_tokens(processor.tokenizer, family=family, thinking=thinking,
                                   continuation=continuation)
    with torch.inference_mode():
        left = Branch(model, video, device, dtype)
        right = Branch(model, question, device, dtype) if alpha else None
        lv, lq = left.logits(), right.logits() if right else None
        for index in range(max_new_tokens):
            scores = combine_logits(lv, lq, alpha=alpha, beta=beta, suppress_tokens=suppressed)
            if controller:
                scores = controller(left.sequence, scores)
            if not torch.isfinite(scores).any(dim=-1).all():
                raise ValueError('no valid decoding candidates after reasoning control')
            probabilities = torch.softmax(scores, dim=-1)
            if (not torch.isfinite(probabilities).all()
                    or not (probabilities.sum(dim=-1) > 0).all()):
                raise ValueError('softmax produced invalid decoding probabilities')
            token = probabilities.argmax(dim=-1)
            tid = int(token.item())
            generated.append(tid)
            if tid in stop or index + 1 == max_new_tokens:
                break
            lv, lq = left.logits(token), right.logits(token) if right else None
            if right and left.kwargs.get('past_key_values') is right.kwargs.get('past_key_values'):
                raise RuntimeError('CD branches unexpectedly share a KV cache')
    return generated


def generate_answer(model, processor, target, *, args, dtype, on_checkpoint, on_truncated=None):
    """Persist one answer and small phase summaries; keep continuation inputs in memory."""
    started = time.perf_counter()
    result = {'status': 'running', 'phases': [], 'final_answer_retry_count': 0}
    prefill = ''
    thinking = not args.disable_thinking
    try:
        media = load_frames(target['video_path'], args.model_family)
        messages = target['messages']
        question_messages = target['question_messages']
        for phase in range(2):
            budget = args.max_new_tokens if phase == 0 else FINAL_ANSWER_CONTINUATION_MAX_TOKENS
            think_budget = args.thinking_token_budget if phase == 0 and thinking else None
            stage = {'stage': 'initial' if phase == 0 else 'continuation',
                     'max_tokens': budget, 'thinking_token_budget': think_budget, 'finish_reason': 'error'}
            result['phases'].append(stage)
            video = prepare(processor, messages, args, media=media, continuation=bool(phase))
            check_context(model, processor, video, budget)
            stop = eos_ids(model, processor)
            tick = time.perf_counter()
            question = None
            if args.alpha:
                question = prepare(processor, question_messages, args, continuation=bool(phase))
                check_context(model, processor, question, budget)
            ids = decode(model, processor, video, question, family=args.model_family,
                         alpha=args.alpha, beta=args.beta, max_new_tokens=budget,
                         thinking_token_budget=think_budget, stop=stop, device=args.device, dtype=dtype,
                         thinking=thinking, continuation=bool(phase))
            body, reasoning = parsed(processor, ids, stop, args.model_family,
                                     continuation=bool(phase), thinking=thinking)
            stage.update(generated_tokens=len(ids), finish_reason='stop' if ids and ids[-1] in stop else 'length',
                         seconds=round(time.perf_counter() - tick, 6))
            result.update(raw_answer=prefill + body, finish_reason=stage['finish_reason'])
            if reasoning and not phase:
                result['reasoning_content'] = reasoning
            else:
                result.pop('reasoning_content', None)
            error = None
            if stage['finish_reason'] == 'length':
                error = 'max_tokens_truncated' if phase == 0 else 'final_answer_continuation_max_tokens_truncated'
                if on_truncated:
                    text = (reasoning + '\n' if reasoning else '') + result['raw_answer']
                    on_truncated({**stage, 'answer_text': text, 'final_answer_retry_count': phase})
            else:
                try:
                    result['final_answer'] = extract_final_answer(result['raw_answer'])
                except MissingFinalAnswerError:
                    error = 'missing_final_answer'
            if error:
                stage['diagnostic'] = error
            else:
                result['status'] = 'ok'
                break
            if phase:
                raise ValueError(f'Final-answer continuation failed: {error}')
            # Match the main experiment's assistant prefill, including separate reasoning.
            prefill = (reasoning + '\n' if reasoning else '') + body + '\n' + FINAL_ANSWER_PREFIX
            assistant = {'role': 'assistant', 'content': prefill}
            messages = target['messages'] + [assistant]
            question_messages = target['question_messages'] + [assistant]
            result['final_answer_retry_count'] = 1
            on_checkpoint(result)
    except KeyboardInterrupt:
        result.update(status='interrupted', error={'type': 'KeyboardInterrupt', 'message': 'QA interrupted'})
        result['seconds'] = round(time.perf_counter() - started, 6)
        on_checkpoint(result)
        raise
    except Exception as exc:
        result.update(status='failed', error={'type': type(exc).__name__, 'message': str(exc)[:1000]})
    result['seconds'] = round(time.perf_counter() - started, 6)
    return result
