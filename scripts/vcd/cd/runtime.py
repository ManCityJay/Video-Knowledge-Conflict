"""Serial local QA with isolated CD branches and one assistant continuation."""
from __future__ import annotations

import time

from vconflict_pipeline.qa import (
    FINAL_ANSWER_CONTINUATION_MAX_TOKENS, FINAL_ANSWER_PREFIX,
    MissingFinalAnswerError, extract_final_answer,
)
from .adapters import Branch, eos_ids, native_generate
from .control import ReasoningControl, suppressed_tokens
from .core import combine_logits
from .video import load_frames, prepare_inputs, question_messages


def decode(model, processor, video, question, *, family, alpha, beta,
           max_new_tokens, thinking_token_budget, stop, device, dtype, thinking=True):
    import torch
    generated = []
    controller = (ReasoningControl(processor.tokenizer, video['input_ids'][0].tolist(),
                                   family=family, budget=thinking_token_budget) if thinking else None)
    suppressed = suppressed_tokens(processor.tokenizer, family=family, thinking=thinking)
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


def parsed(processor, ids, stop, family, *, continuation=False, thinking=True):
    tokens = ids[:-1] if ids and ids[-1] in stop else ids
    raw = processor.tokenizer.decode(tokens, skip_special_tokens=False,
                                     clean_up_tokenization_spaces=False)
    reasoning = None
    if continuation or family == 'cosmos':
        body = processor.tokenizer.decode(tokens, skip_special_tokens=True,
                                         clean_up_tokenization_spaces=False)
    else:
        # Reuse the very parsers used by the main vLLM endpoints.
        if family == 'qwen':
            from vllm.parser.qwen3 import Qwen3Parser
            parser = Qwen3Parser(processor.tokenizer, chat_template_kwargs={'enable_thinking': thinking})
        else:
            from vllm.parser.gemma4 import Gemma4Parser
            parser = Gemma4Parser(processor.tokenizer, chat_template_kwargs={'enable_thinking': thinking})
        reasoning, body = parser.extract_reasoning(raw, None)
        body = body or ''
    return body, reasoning


def check_context(model, processor, inputs, budget):
    config = model.config.get_text_config()
    limits = [getattr(config, 'max_position_embeddings', 0),
              getattr(processor.tokenizer, 'model_max_length', 0)]
    limits = [n for n in limits if isinstance(n, int) and 0 < n < 10**9]
    if limits and inputs['input_ids'].shape[1] + budget > min(limits):
        raise ValueError(f"Insufficient context: {inputs['input_ids'].shape[1]} prompt tokens + "
                         f"{budget} output tokens exceeds {min(limits)}; inputs are never cropped")


def generate_answer(model, processor, target, *, method, args, dtype, on_checkpoint, on_truncated=None):
    """Persist one answer and small phase summaries; keep continuation inputs in memory."""
    started = time.perf_counter()
    result = {'status': 'running', 'phases': [], 'final_answer_retry_count': 0}
    prefill = ''
    thinking = not args.disable_thinking
    try:
        media = load_frames(target['video_path'], args.model_family)
        messages = target['messages']
        for phase in range(2):
            budget = args.max_new_tokens if phase == 0 else FINAL_ANSWER_CONTINUATION_MAX_TOKENS
            think_budget = args.thinking_token_budget if phase == 0 and thinking else None
            stage = {'stage': 'initial' if phase == 0 else 'continuation',
                     'max_tokens': budget, 'thinking_token_budget': think_budget, 'finish_reason': 'error'}
            result['phases'].append(stage)
            video = prepare_inputs(processor, messages, family=args.model_family,
                                   media=media, continuation=bool(phase), thinking=thinking)
            check_context(model, processor, video, budget)
            stop = eos_ids(model, processor)
            tick = time.perf_counter()
            question = None
            if method == 'cd' and args.alpha:
                question = prepare_inputs(processor, question_messages(messages),
                                          family=args.model_family, continuation=bool(phase), thinking=thinking)
                check_context(model, processor, question, budget)
            if method == 'cd':
                ids = decode(model, processor, video, question, family=args.model_family,
                             alpha=args.alpha, beta=args.beta, max_new_tokens=budget,
                             thinking_token_budget=think_budget, stop=stop, device=args.device, dtype=dtype,
                             thinking=thinking)
            else:
                ids = native_generate(model, processor, video, family=args.model_family,
                                      max_new_tokens=budget, thinking_token_budget=think_budget,
                                      device=args.device, dtype=dtype, thinking=thinking)
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
            messages = target['messages'] + [{'role': 'assistant', 'content': prefill}]
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
