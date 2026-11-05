"""TCD/SEASON batch token selection, stopping, reasoning budgets and telemetry."""
from __future__ import annotations

import time
import uuid

from vconflict_pipeline.common import utc_now
from vconflict_pipeline.qa import FINAL_ANSWER_CONTINUATION_MAX_TOKENS
from .adapters import eos_ids
from .batching import collate
from .batch_tuning import BatchMemoryPressure
from .control import ReasoningControl, suppressed_tokens
from .generation import check_context
from .storage import atomic_json


def decode_batch(model, processor, states, *, args, dtype, phase):
    from .methods import get_method
    method = get_method(args.method)
    import torch
    started = time.perf_counter()
    batch_id = uuid.uuid4().hex
    positive = collate([s['positive'] for s in states], processor.tokenizer)
    negative = (collate([s['negative'] for s in states], processor.tokenizer)
                if states[0]['negative'] is not None else None)
    budget = args.max_new_tokens if phase == 0 else FINAL_ANSWER_CONTINUATION_MAX_TOKENS
    think_budget = args.thinking_token_budget if phase == 0 and not args.disable_thinking else None
    for inputs in [positive, negative]:
        if inputs is not None:
            check_context(model, processor, inputs, budget)
    stop = eos_ids(model, processor)
    batch = len(states)
    active = [True] * batch
    ids, seconds = [[] for _ in states], [0.] * batch
    thinking = not args.disable_thinking
    controllers = [ReasoningControl(processor.tokenizer, positive['input_ids'][i].tolist(),
                                    family=args.model_family, budget=think_budget) if thinking else None
                   for i in range(batch)]
    suppressed = suppressed_tokens(processor.tokenizer, family=args.model_family,
                                   thinking=thinking, continuation=bool(phase))
    torch.cuda.synchronize(args.device)
    torch.cuda.reset_peak_memory_stats(args.device)
    with torch.inference_mode(), method.Decoder(
            model, processor, states, positive, negative, args, dtype) as decoder:
        for step in range(budget):
            scores = decoder.scores(suppressed, active)
            for index, controller in enumerate(controllers):
                if active[index] and controller:
                    scores[index:index + 1] = controller(decoder.sequence[index:index + 1],
                                                         scores[index:index + 1])
            if not torch.isfinite(scores).any(dim=-1).all():
                raise ValueError('No valid batched decoding candidates')
            token = scores.argmax(-1)
            emitted = token.tolist()
            finished = []
            for index, tid in enumerate(emitted):
                if active[index]:
                    ids[index].append(tid)
                    if tid in stop or step + 1 == budget:
                        active[index] = False
                        finished.append(index)
                else:
                    # Finished rows remain inert padding in a static batch, never saved as output.
                    token[index] = min(stop)
            if finished:
                torch.cuda.synchronize(args.device)
                elapsed = time.perf_counter() - started
                for index in finished:
                    seconds[index] = elapsed
            if (step + 1) % 64 == 0:
                free, total = torch.cuda.mem_get_info(args.device)
                allocated = torch.cuda.memory_allocated(args.device)
                reserved = torch.cuda.memory_reserved(args.device)
                elapsed = time.perf_counter() - started
                live = {'updated_at': utc_now(), 'run_id': args.run_id, 'batch_id': batch_id,
                        'method': args.method, 'model_family': args.model_family, 'phase': phase,
                        'batch_size': batch, 'step': step + 1, 'active': sum(active),
                        'effective_tokens': sum(map(len, ids)), 'wall_seconds': elapsed,
                        'effective_tokens_per_second': sum(map(len, ids)) / elapsed,
                        'allocated_bytes': allocated, 'reserved_bytes': reserved,
                        'free_device_bytes': free}
                atomic_json(args.output / 'decode_live.json', live)
                if batch > 1 and free + reserved - allocated < max(2 * 1024**3, total * .04):
                    raise BatchMemoryPressure('Low memory headroom during long-sequence decoding')
                print(f'Decode: method={args.method} phase={phase} batch={batch} '
                      f'step={step + 1}/{budget} active={sum(active)} '
                      f'elapsed={time.perf_counter() - started:.1f}s', flush=True)
            if not any(active):
                break
            decoder.advance(token)
        metadata = decoder.metadata(ids)
    torch.cuda.synchronize(args.device)
    audit = {'batch_id': batch_id, 'phase': 'initial' if phase == 0 else 'continuation',
             'batch_size': batch, 'wall_seconds': round(time.perf_counter() - started, 6),
             'generated_tokens': sum(map(len, ids)), 'decode_steps': max(map(len, ids)),
             'active_token_fraction': sum(map(len, ids)) / (batch * max(map(len, ids))),
             'peak_allocated_bytes': torch.cuda.max_memory_allocated(args.device),
             'peak_reserved_bytes': torch.cuda.max_memory_reserved(args.device)}
    return ids, seconds, metadata, audit

