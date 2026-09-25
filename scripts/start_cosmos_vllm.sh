#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"

if ! command -v conda >/dev/null 2>&1; then
  echo "找不到 conda；请先将 Conda 的 bin 目录加入 PATH。" >&2
  exit 1
fi

conda_base="$(conda info --base)"
source "$conda_base/etc/profile.d/conda.sh"
conda activate vllm

export HF_HOME=/cache/huggingface
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"
export VLLM_USE_FLASHINFER_SAMPLER=0
export CUDA_VISIBLE_DEVICES=0

VIDEO_ROOT="${VIDEO_ROOT:-$repo_root/videos}"
if [[ ! -d "$VIDEO_ROOT" ]]; then
  echo "视频目录不存在：$VIDEO_ROOT" >&2
  exit 1
fi
VIDEO_ROOT="$(cd -- "$VIDEO_ROOT" && pwd -P)"

exec vllm serve nvidia/Cosmos3-Nano \
  --tensor-parallel-size 1 \
  --mm-encoder-tp-mode data \
  --async-scheduling \
  --allowed-local-media-path "$VIDEO_ROOT" \
  --media-io-kwargs '{"video": {"video_backend": "opencv", "num_frames": -1, "fps": -1}}' \
  --max-num-seqs 4 \
  --host 127.0.0.1 --port 8000
