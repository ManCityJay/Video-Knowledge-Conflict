#!/usr/bin/env bash
set -euo pipefail
cd /home/ma-user/workspace/Video-Knowledge-Conflict
/home/ma-user/miniconda3/envs/mcd-v1/bin/python -u scripts/mcd_v1/run_lambda_sweep.py \
  --manifest results/mcd_v1/pilot_10_v1/manifest.json \
  --output-dir results/mcd_v1/lambda_sweep_20_v1 \
  --model /cache/huggingface/hub/models--nvidia--Cosmos3-Nano/snapshots/e59a53c25979a090fa8706c9acc0c254a6e89b92 \
  --device cuda:1 --beta 0.1 --fps 4 --max-new-tokens 512 "$@"
