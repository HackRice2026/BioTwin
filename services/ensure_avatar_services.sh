#!/usr/bin/env bash
# Watchdog for the two avatar GPU services (face lip-sync + body gestures).
# Idempotent: safe to run repeatedly (cron does, every few minutes, plus at
# boot) -- only acts when a service is actually down. Recreates the tmux
# session fresh rather than trying to reuse a dead one, since both
# services' start.sh end in `exec`, which replaces the pane's shell -- once
# that process dies for any reason, the pane has nothing left to return a
# prompt to, and the old session is unusable even if tmux still lists it.
set -u

ensure_service() {
  local name="$1" port="$2" start_script="$3"
  if curl -s -m 3 "http://127.0.0.1:${port}/health" > /dev/null 2>&1; then
    return 0
  fi
  echo "$(date -Is) ${name}: not responding on ${port}, restarting"
  tmux kill-session -t "${name}" 2>/dev/null
  tmux new-session -d -s "${name}"
  tmux send-keys -t "${name}" "bash ${start_script}" Enter
}

ensure_service avatar-face 8765 /data/saurav/avatar_face_service/start.sh
ensure_service avatar-body 8766 /data/saurav/avatar_body_service/start.sh
