"""Answer parsing and context limits shared by all decoding methods."""
from __future__ import annotations


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

