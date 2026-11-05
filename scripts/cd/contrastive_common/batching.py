"""Left-padded tensor batches with per-sample multimodal geometry."""
from __future__ import annotations


def signature(inputs):
    import torch
    # Text lengths can differ; visual layouts must match within a tensor batch.
    return tuple((key, str(value.dtype), tuple(value.shape), tuple(value.flatten().tolist()) if key == 'video_grid_thw' else None)
                 for key, value in sorted(inputs.items())
                 if key not in ('input_ids', 'attention_mask', 'mm_token_type_ids', 'token_type_ids')
                 and isinstance(value, torch.Tensor))


def collate(inputs, tokenizer):
    import torch
    import torch.nn.functional as F
    keys = set(inputs[0])
    if any(set(row) != keys for row in inputs):
        raise ValueError('Batch input fields differ')
    width = max(row['input_ids'].shape[1] for row in inputs)
    pad = tokenizer.pad_token_id
    if pad is None:
        pad = tokenizer.eos_token_id
    if pad is None:
        raise ValueError('Batching needs a pad or EOS token')
    result = {}
    sequence_keys = {'input_ids', 'attention_mask', 'mm_token_type_ids', 'token_type_ids'}
    for key in keys:
        values = [row[key] for row in inputs]
        if not all(isinstance(v, torch.Tensor) for v in values):
            raise ValueError(f'Unsupported non-tensor processor field: {key}')
        if key in sequence_keys:
            values = [F.pad(v, (width - v.shape[1], 0), value=pad if key == 'input_ids' else 0)
                      for v in values]
        result[key] = torch.cat(values, dim=0)
    if 'attention_mask' not in result:
        result['attention_mask'] = torch.cat([
            F.pad(torch.ones_like(row['input_ids']), (width - row['input_ids'].shape[1], 0))
            for row in inputs], dim=0)
    return result
