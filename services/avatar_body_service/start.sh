#!/usr/bin/env bash
set -euo pipefail

cd /data/saurav/avatar_body_service
source /data/saurav/envs/emage/bin/activate
export PYTHONPATH="/data/saurav/emage:${PYTHONPATH:-}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8766}"
