#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname -- "$0")/../.."
/home/ma-user/miniconda3/envs/mcd-v1/bin/python -u scripts/mcd_v1/run_lambda_sweep.py \
  --manifest results/mcd_v1/heldout_physics_v1_manifest.json \
  --output-dir results/mcd_v1/heldout_physics_v1 \
  --model /cache/huggingface/hub/models--nvidia--Cosmos3-Nano/snapshots/e59a53c25979a090fa8706c9acc0c254a6e89b92 \
  --device cuda:1 --beta 0.1 --fps 4 --max-new-tokens 512 --lambdas 0 0.2 0.3 "$@"
