#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/workspace/media-aggregator"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.runpod}"
BOOTSTRAP_SCRIPT="$ROOT_DIR/deploy/runpod/bootstrap.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1 || ! command -v pm2 >/dev/null 2>&1 || ! command -v ollama >/dev/null 2>&1; then
  if [[ ! -x "$BOOTSTRAP_SCRIPT" ]]; then
    echo "Missing bootstrap script: $BOOTSTRAP_SCRIPT" >&2
    exit 1
  fi
  bash "$BOOTSTRAP_SCRIPT"
fi

cd "$ROOT_DIR"
set -a
source "$ENV_FILE"
set +a
export OLLAMA_MODELS="${OLLAMA_MODELS:-$ROOT_DIR/.ollama/models}"

mkdir -p "$ROOT_DIR/data" "$ROOT_DIR/logs" "$OLLAMA_MODELS"

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

"$ROOT_DIR/.venv/bin/pip" install --upgrade pip wheel
"$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"

cd "$ROOT_DIR/frontend"
if [[ ! -d node_modules ]]; then
  npm ci
fi
NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL}" \
NEXT_PUBLIC_EXPORT_BASE_URL="${NEXT_PUBLIC_EXPORT_BASE_URL}" \
  npm run build
cd "$ROOT_DIR"

pm2 delete media-ollama media-backend media-frontend >/dev/null 2>&1 || true

pm2 start "bash -lc 'export OLLAMA_HOST=0.0.0.0:11434 OLLAMA_MODELS=\"$OLLAMA_MODELS\" && ollama serve'" --name media-ollama

for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if [[ -n "${OLLAMA_MODEL:-}" ]]; then
  ollama pull "${OLLAMA_MODEL}"
fi

pm2 start "bash -lc 'cd \"$ROOT_DIR\" && set -a && source \"$ENV_FILE\" && set +a && PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000'" --name media-backend
pm2 start "bash -lc 'cd \"$ROOT_DIR/frontend\" && export NEXT_PUBLIC_API_BASE_URL=\"$NEXT_PUBLIC_API_BASE_URL\" NEXT_PUBLIC_EXPORT_BASE_URL=\"$NEXT_PUBLIC_EXPORT_BASE_URL\" && npm run start -- --hostname 0.0.0.0 --port 3000'" --name media-frontend

pm2 save
pm2 status
