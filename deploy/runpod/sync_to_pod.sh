#!/usr/bin/env bash
set -euo pipefail

POD_HOST="${1:?Usage: sync_to_pod.sh <ip> <ssh_port>}"
POD_PORT="${2:?Usage: sync_to_pod.sh <ip> <ssh_port>}"
REMOTE_DIR="${REMOTE_DIR:-/workspace/media-aggregator}"

rsync -az --delete \
  --exclude '.venv' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/.next' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.pyo' \
  --exclude '*.db' \
  --exclude '.env' \
  --exclude '.env.runpod' \
  --exclude 'tmp' \
  -e "ssh -i $HOME/.ssh/id_ed25519 -p ${POD_PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
  ./ "root@${POD_HOST}:${REMOTE_DIR}"
