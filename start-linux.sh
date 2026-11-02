#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Install Python 3.10+ and its venv/pip components inside Linux/WSL2 first.' >&2
  exit 1
fi
exec python3 tools/portable.py "${1:-start}"
