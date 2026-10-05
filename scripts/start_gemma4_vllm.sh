#!/usr/bin/env bash
set -euo pipefail

# 默认复用 vllm 环境：2 × A100 80GB，BF16，32K 上下文，端口 8001。
# 只查看命令：DRY_RUN=1 bash scripts/start_gemma4_vllm.sh
# 单卡示例：CUDA_VISIBLE_DEVICES=1 TENSOR_PARALLEL_SIZE=1 MAX_MODEL_LEN=8192 \
#   MAX_NUM_SEQS=1 GPU_MEMORY_UTILIZATION=0.90 bash scripts/start_gemma4_vllm.sh

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"

if ! command -v conda >/dev/null 2>&1; then
  echo "找不到 conda；请先将 Conda 的 bin 目录加入 PATH。" >&2
  exit 1
fi

conda_base="$(conda info --base)"
source "$conda_base/etc/profile.d/conda.sh"
conda activate "${GEMMA_CONDA_ENV:-vllm}"

export HF_HOME="${HF_HOME:-/cache/huggingface}"
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# 当前机器没有匹配的 nvcc，沿用 Cosmos 环境中已验证的采样回退。
export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"

GEMMA_MODEL="${GEMMA_MODEL:-google/gemma-4-31B-it}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-2}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-2}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.85}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8001}"

cmd=(
  "$CONDA_PREFIX/bin/vllm" serve "$GEMMA_MODEL"
  --served-model-name google/gemma-4-31B-it
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE"
  --dtype bfloat16
  --max-model-len "$MAX_MODEL_LEN"
  --max-num-seqs "$MAX_NUM_SEQS"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --reasoning-parser gemma4
  --default-chat-template-kwargs '{"enable_thinking":false}'
  --async-scheduling
  --host "$VLLM_HOST" --port "$VLLM_PORT"
)

# 官方仓库固定到本次核对的版本；本地目录默认不加 revision。
if [[ "$GEMMA_MODEL" == "google/gemma-4-31B-it" ]]; then
  cmd+=(--revision "${GEMMA_REVISION:-842da3794eaa0b77d5f08bae87a17459d91ff475}")
elif [[ -n "${GEMMA_REVISION:-}" ]]; then
  cmd+=(--revision "$GEMMA_REVISION")
fi

if [[ "${TEXT_ONLY:-0}" == "1" ]]; then
  cmd+=(--limit-mm-per-prompt '{"image":0,"video":0,"audio":0}')
else
  MEDIA_ROOT="${MEDIA_ROOT:-$repo_root/videos}"
  if [[ ! -d "$MEDIA_ROOT" ]]; then
    echo "媒体目录不存在：$MEDIA_ROOT；可设置 MEDIA_ROOT 或 TEXT_ONLY=1。" >&2
    exit 1
  fi
  MEDIA_ROOT="$(cd -- "$MEDIA_ROOT" && pwd -P)"
  cmd+=(
    --allowed-local-media-path "$MEDIA_ROOT"
    --limit-mm-per-prompt '{"image":4,"video":1,"audio":0}'
    --mm-processor-kwargs '{"max_soft_tokens":280}'
    --media-io-kwargs '{"video":{"video_backend":"opencv","num_frames":32,"fps":1}}'
  )
fi

# 追加参数可以覆盖 vLLM 的同名标量参数。
cmd+=("$@")
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  printf 'CUDA_VISIBLE_DEVICES=%q HF_HOME=%q LD_LIBRARY_PATH=%q VLLM_USE_FLASHINFER_SAMPLER=%q ' \
    "$CUDA_VISIBLE_DEVICES" "$HF_HOME" "$LD_LIBRARY_PATH" "$VLLM_USE_FLASHINFER_SAMPLER"
  printf '%q ' "${cmd[@]}"
  printf '\n'
  exit 0
fi

mkdir -p -- "$HF_HOME"
exec "${cmd[@]}"
