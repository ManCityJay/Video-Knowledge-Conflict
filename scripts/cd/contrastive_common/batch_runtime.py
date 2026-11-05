"""Batched TCD/SEASON decoding and the main experiment's one-shot recovery."""
from __future__ import annotations

from collections import defaultdict
import gc
import time
import uuid

from vconflict_pipeline.qa import (
    FINAL_ANSWER_CONTINUATION_MAX_TOKENS, FINAL_ANSWER_PREFIX,
    MissingFinalAnswerError, extract_final_answer,
)
from .adapters import eos_ids
from .methods import get_method
from .decoding import decode_batch
from .batching import signature
from .generation import check_context, parsed
from .batch_tuning import BatchMemoryPressure, BatchTuner


def generate_answers(model, processor, targets, *, args, dtype, on_checkpoint, on_truncated, on_batch):
    """Bound CPU preparation, bucket visual geometry, split OOM batches, recover once."""
    method = get_method(args.method)
    import torch
    limit = [args.max_batch_size if args.batch_size == 'auto' else int(args.batch_size)]
    tuner = BatchTuner(args) if args.autotune_batch else None

    def current_limit():
        if tuner:
            limit[0] = tuner.desired()
        return limit[0]

    def fail(state, exc):
        state['result'].update(status='failed', error={'type': type(exc).__name__, 'message': str(exc)[:1000]})
        return state

    def prepare(state, phase):
        tick = time.perf_counter()
        try:
            full, negative, sampling = method.prepare(
                processor, state['target'], args, messages=state['messages'], continuation=bool(phase),
                sample_cache=state['media_cache'])
            budget = args.max_new_tokens if phase == 0 else FINAL_ANSWER_CONTINUATION_MAX_TOKENS
            for inputs in (full, negative):
                if inputs is not None:
                    check_context(model, processor, inputs, budget)
            state.update(positive=full, negative=negative)
            state['result']['sampling'] = sampling
        finally:
            state['result']['seconds'] += time.perf_counter() - tick

    def decode_group(group, phase):
        # Retry only resource failures, with exactly the same inputs and decoding budget.
        ceiling = current_limit()
        if len(group) > ceiling:
            offset = 0
            while offset < len(group):
                width = min(current_limit(), len(group) - offset)
                yield from decode_group(group[offset:offset + width], phase)
                offset += width
            return
        tick = time.perf_counter()
        oom = None
        try:
            value = decode_batch(model, processor, group, args=args, dtype=dtype, phase=phase)
        except KeyboardInterrupt:
            elapsed = time.perf_counter() - tick
            for state in group:
                state['result']['seconds'] += elapsed
            raise
        except (torch.OutOfMemoryError, BatchMemoryPressure) as exc:
            oom = str(exc)[:1000]
        except Exception as exc:
            # A bad sample should not fail unrelated samples sharing its bucket.
            if len(group) == 1:
                state = group[0]
                state['result']['seconds'] += time.perf_counter() - tick
                yield fail(state, exc), None
                return
            # Do not recurse in the except suite: traceback retains GPU tensors.
            value = None
        else:
            ids, seconds, metadata, audit = value
            audit['targets'] = [s['target']['label'] for s in group]
            on_batch(audit)
            if tuner:
                tuner.observe(audit)
            for state, tokens, elapsed, extra in zip(group, ids, seconds, metadata):
                state['result']['seconds'] += elapsed
                yield state, (tokens, extra, audit, elapsed)
            return
        gc.collect()
        torch.cuda.empty_cache()
        elapsed = time.perf_counter() - tick
        for state in group:
            state['result']['seconds'] += elapsed
        if oom is not None:
            if tuner:
                tuner.failure(len(group), elapsed, oom)
            on_batch({'batch_id': uuid.uuid4().hex, 'phase': phase, 'batch_size': len(group),
                      'wall_seconds': round(elapsed, 6), 'status': 'oom', 'error': oom,
                      'targets': [s['target']['label'] for s in group]})
            for state in group:
                state['result']['oom_retries'] = state['result'].get('oom_retries', 0) + 1
                state['result']['oom_retry_seconds'] = state['result'].get('oom_retry_seconds', 0.) + elapsed
            if len(group) == 1:
                yield fail(group[0], RuntimeError('CUDA OOM at batch size 1: ' + oom)), None
                return
            limit[0] = max(1, min(limit[0], len(group) // 2))
            print(f'CUDA OOM: reducing batch ceiling to {limit[0]}', flush=True)
        if len(group) > 1:
            middle = len(group) // 2
            yield from decode_group(group[:middle], phase)
            yield from decode_group(group[middle:], phase)

    def process(window):
        pending = window
        for phase in range(2):
            buckets = defaultdict(list)
            for state in pending:
                try:
                    prepare(state, phase)
                except Exception as exc:
                    yield fail(state, exc)
                    continue
                key = (signature(state['positive']),
                       signature(state['negative']) if state['negative'] is not None else None)
                buckets[key].append(state)
            recovery = []
            for group in buckets.values():
                for state, decoded in decode_group(group, phase):
                    result = state['result']
                    state.pop('positive', None)
                    state.pop('negative', None)
                    if decoded is None:
                        yield state
                        continue
                    tokens, extra, audit, elapsed = decoded
                    budget = args.max_new_tokens if phase == 0 else FINAL_ANSWER_CONTINUATION_MAX_TOKENS
                    stage = {'stage': 'initial' if phase == 0 else 'continuation',
                             'max_tokens': budget,
                             'thinking_token_budget': args.thinking_token_budget if phase == 0 and not args.disable_thinking else None,
                             'generated_tokens': len(tokens), 'seconds': round(elapsed, 6),
                             'finish_reason': 'stop' if tokens and tokens[-1] in stop else 'length',
                             'batch_id': audit['batch_id'], 'batch_size': audit['batch_size'],
                             'batch_wall_seconds': audit['wall_seconds'], **extra}
                    result['phases'].append(stage)
                    parse_started = time.perf_counter()
                    try:
                        body, reasoning = parsed(processor, tokens, stop, args.model_family,
                                                 continuation=bool(phase), thinking=not args.disable_thinking)
                        result.update(raw_answer=state['prefill'] + body, finish_reason=stage['finish_reason'])
                        if reasoning and not phase:
                            result['reasoning_content'] = reasoning
                        else:
                            result.pop('reasoning_content', None)
                        error = None
                        if stage['finish_reason'] == 'length':
                            error = ('max_tokens_truncated' if phase == 0
                                     else 'final_answer_continuation_max_tokens_truncated')
                            stage['diagnostic'] = error
                            on_truncated(state['index'], {**stage, 'answer_text':
                                (reasoning + '\n' if reasoning else '') + result['raw_answer'],
                                'final_answer_retry_count': phase})
                        else:
                            try:
                                result['final_answer'] = extract_final_answer(result['raw_answer'])
                                if phase and not body.strip():
                                    raise MissingFinalAnswerError('Empty continuation')
                            except MissingFinalAnswerError:
                                error = 'missing_final_answer'
                                stage['diagnostic'] = error
                        result['seconds'] += time.perf_counter() - parse_started
                        if error is None:
                            result['status'] = 'ok'
                            yield state
                        elif phase:
                            yield fail(state, ValueError('Final-answer continuation failed: ' + error))
                        else:
                            state['prefill'] = (reasoning + '\n' if reasoning else '') + body + '\n' + FINAL_ANSWER_PREFIX
                            state['messages'] = state['target']['messages'] + [
                                {'role': 'assistant', 'content': state['prefill']}]
                            result['final_answer_retry_count'] = 1
                            result['final_answer_continuation'] = {
                                'initial_raw_answer': body, 'initial_reasoning_content': reasoning,
                                'assistant_prefill': state['prefill'],
                                'max_tokens': FINAL_ANSWER_CONTINUATION_MAX_TOKENS,
                                'thinking_token_budget': None, 'continue_final_message': True,
                                'add_generation_prompt': False, 'echo': False}
                            on_checkpoint(state['index'], result)
                            recovery.append(state)
                    except Exception as exc:
                        yield fail(state, exc)
            pending = recovery

    stop = eos_ids(model, processor)
    offset = 0
    while offset < len(targets):
        window = []
        window_size = max(32, current_limit()) if tuner else limit[0]
        for index in range(offset, min(len(targets), offset + window_size)):
            window.append({'index': index, 'target': targets[index], 'messages': targets[index]['messages'],
                           'prefill': '', 'media_cache': {}, 'result': {'status': 'running', 'phases': [],
                           'final_answer_retry_count': 0, 'seconds': 0.,
                           'timing_protocol': 'sample_service_latency_v1'}})
        offset += len(window)
        try:
            for state in process(window):
                state['result']['seconds'] = round(state['result']['seconds'], 6)
                yield state['index'], state['result']
        except KeyboardInterrupt:
            for state in window:
                if state['result']['status'] == 'running':
                    state['result'].update(status='interrupted', error={
                        'type': 'KeyboardInterrupt', 'message': 'QA interrupted'})
                    on_checkpoint(state['index'], state['result'])
            raise

    if tuner:
        tuner.finish()
