#!/usr/bin/env bash
set -euo pipefail

# vLLM 0.29.0 / torch 2.13.0+cu130；默认使用 GPU 0 单卡。
# 双卡示例：CUDA_VISIBLE_DEVICES=0,1 TENSOR_PARALLEL_SIZE=2 bash scripts/start_cosmos_vllm.sh
# 可追加 vLLM 参数，例如：bash scripts/start_cosmos_vllm.sh --max-model-len 32768
# 显存预算可调整：GPU_MEMORY_UTILIZATION=0.85 bash scripts/start_cosmos_vllm.sh

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"

if ! command -v conda >/dev/null 2>&1; then
  echo "找不到 conda；请先将 Conda 的 bin 目录加入 PATH。" >&2
  exit 1
fi

conda_base="$(conda info --base)"
source "$conda_base/etc/profile.d/conda.sh"
conda activate vllm

export HF_HOME="${HF_HOME:-/cache/huggingface}"
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# 未配置匹配的 nvcc 时，默认使用回退采样器。
export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-4}"
# 按总显存计算；默认留出空间供同卡其他进程使用。
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.92}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"

VIDEO_ROOT="${VIDEO_ROOT:-$repo_root/videos}"
if [[ ! -d "$VIDEO_ROOT" ]]; then
  echo "视频目录不存在：$VIDEO_ROOT" >&2
  exit 1
fi
VIDEO_ROOT="$(cd -- "$VIDEO_ROOT" && pwd -P)"

# 0.29.0 原生支持 Cosmos3ForConditionalGeneration，无需旧的架构覆盖参数。
exec "$CONDA_PREFIX/bin/vllm" serve nvidia/Cosmos3-Nano \
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE" \
  --dtype bfloat16 \
  --mm-encoder-tp-mode data \
  --async-scheduling \
  --allowed-local-media-path "$VIDEO_ROOT" \
  --media-io-kwargs '{"video": {"video_backend": "opencv", "num_frames": -1, "fps": -1}}' \
  --max-num-seqs "$MAX_NUM_SEQS" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --host "$VLLM_HOST" --port "$VLLM_PORT" \
  "$@"
