#!/usr/bin/env bash
set -euo pipefail

cd /data/saurav/avatar_face_service
source /data/saurav/envs/avatar_face_lipsync/bin/activate

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8765}"
