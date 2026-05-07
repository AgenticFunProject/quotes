#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "${ROOT_DIR}/.venv/bin/python" ]; then
  "${ROOT_DIR}/scripts/bootstrap-venv.sh"
fi

exec "${ROOT_DIR}/.venv/bin/python" -m pytest tests -q "$@"
