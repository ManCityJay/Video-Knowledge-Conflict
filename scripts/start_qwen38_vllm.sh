#!/usr/bin/env bash
set -euo pipefail

# Qwen3.8-27B：复用 vllm 环境，默认单张 A100 80GB，BF16，64K，端口 8002。
# 启动：bash scripts/start_qwen38_vllm.sh
# 换卡：CUDA_VISIBLE_DEVICES=1 bash scripts/start_qwen38_vllm.sh
# 本地目录：QWEN_MODEL=/实际模型目录 bash scripts/start_qwen38_vllm.sh
# 只打印命令：DRY_RUN=1 bash scripts/start_qwen38_vllm.sh
# 默认加载视觉模块；TEXT_ONLY=1 仅适用于独立 question-only（无 control filter）。

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"

# dry-run 只构造命令，允许在没有服务器 Conda/vLLM 的机器上检查部署参数。
if [[ "${DRY_RUN:-0}" != "1" ]]; then
  if ! command -v conda >/dev/null 2>&1; then
    echo "找不到 conda；请先将 Conda 的 bin 目录加入 PATH。" >&2
    exit 1
  fi
  conda_base="$(conda info --base)"
  source "$conda_base/etc/profile.d/conda.sh"
  conda activate "${QWEN_CONDA_ENV:-vllm}"
fi

export HF_HOME="${HF_HOME:-/cache/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
# 模型已下载，默认离线加载；缓存缺失时直接报错。
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
if [[ -n "${CONDA_PREFIX:-}" ]]; then
  export LD_LIBRARY_PATH="$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
# 沿用本机缺少匹配 nvcc 时已验证的采样回退。
export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

QWEN_MODEL="${QWEN_MODEL:-Qwen/Qwen3.8-27B}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-65536}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-1}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8002}"

vllm_bin="${CONDA_PREFIX:+$CONDA_PREFIX/bin/}vllm"
if [[ "${DRY_RUN:-0}" != "1" && ! -x "$vllm_bin" ]]; then
  echo "当前 Conda 环境没有 vllm 可执行文件：$vllm_bin" >&2
  exit 1
fi

# 原生支持 Qwen3_5ForConditionalGeneration，无需架构覆盖或 remote code。
# reasoning parser / thinking 开关参考 https://recipes.vllm.ai/Qwen/Qwen3.8-27B
cmd=(
  "$vllm_bin" serve "$QWEN_MODEL"
  --served-model-name Qwen/Qwen3.8-27B
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE"
  --dtype bfloat16
  --override-generation-config '{"max_new_tokens":8192}'
  --max-model-len "$MAX_MODEL_LEN"
  --max-num-seqs "$MAX_NUM_SEQS"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --reasoning-parser qwen3
  --default-chat-template-kwargs '{"enable_thinking":false}'
  --host "$VLLM_HOST" --port "$VLLM_PORT"
)

if [[ "${TEXT_ONLY:-0}" == "1" ]]; then
  cmd+=(--language-model-only)
else
  MEDIA_ROOT="${MEDIA_ROOT:-$repo_root/videos}"
  if [[ ! -d "$MEDIA_ROOT" ]]; then
    echo "媒体目录不存在：$MEDIA_ROOT；可设置 MEDIA_ROOT 或 TEXT_ONLY=1。" >&2
    exit 1
  fi
  MEDIA_ROOT="$(cd -- "$MEDIA_ROOT" && pwd -P)"
  cmd+=(
    --allowed-local-media-path "$MEDIA_ROOT"
    --limit-mm-per-prompt '{"image":0,"video":1,"audio":0}'
    # 加载原始帧，交给模型处理器按官方默认 2 fps 采样一次。
    --media-io-kwargs '{"video":{"video_backend":"opencv","num_frames":-1,"fps":-1}}'
    --mm-processor-kwargs '{"fps":2,"do_sample_frames":true}'
  )
fi
# 首轮关闭 torch.compile / CUDA graph；验收后可设 ENFORCE_EAGER=0。
# eager 模式不保证所有原生算子都无需 JIT 编译。
if [[ "${ENFORCE_EAGER:-1}" == "1" ]]; then
  cmd+=(--enforce-eager)
fi

cmd+=("$@")
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  printf 'CUDA_VISIBLE_DEVICES=%q HF_HOME=%q HF_HUB_CACHE=%q HF_HUB_OFFLINE=%q LD_LIBRARY_PATH=%q VLLM_USE_FLASHINFER_SAMPLER=%q ' \
    "$CUDA_VISIBLE_DEVICES" "$HF_HOME" "$HF_HUB_CACHE" "$HF_HUB_OFFLINE" \
    "${LD_LIBRARY_PATH:-}" "$VLLM_USE_FLASHINFER_SAMPLER"
  printf '%q ' "${cmd[@]}"
  printf '\n'
  exit 0
fi

exec "${cmd[@]}"
