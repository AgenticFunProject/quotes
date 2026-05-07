#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON_BIN="${PYTHON:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  printf 'Missing required interpreter: %s\n' "${PYTHON_BIN}" >&2
  exit 1
fi

if ! "${PYTHON_BIN}" -m venv "${VENV_DIR}"; then
  printf 'Failed to create %s with %s -m venv.\n' "${VENV_DIR}" "${PYTHON_BIN}" >&2
  printf 'Ensure the runtime provides venv support, including python3-venv and ensurepip.\n' >&2
  exit 1
fi

if ! "${VENV_DIR}/bin/python" -m pip --version >/dev/null 2>&1; then
  if ! "${VENV_DIR}/bin/python" -m ensurepip --upgrade >/dev/null 2>&1; then
    printf 'The virtual environment does not include pip.\n' >&2
    printf 'Ensure the runtime provides ensurepip so the repo can bootstrap its dev dependencies.\n' >&2
    exit 1
  fi
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -e "${ROOT_DIR}[dev]"
