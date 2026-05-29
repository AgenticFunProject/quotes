#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "${ROOT_DIR}/.venv/bin/python" ]; then
  "${ROOT_DIR}/scripts/bootstrap-venv.sh"
fi

"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/verify_gherkin_contract.py"
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group smoke --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group quote-readiness --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group lifecycle --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group pricing --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group admin-commercial --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group auth --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group approval --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group validity --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group diagnostics --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile azure --group deployment --dry-run
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/scripts/gherkin_contract.py" run --profile local --group integration-boundary --dry-run
exec "${ROOT_DIR}/.venv/bin/python" -m pytest tests -q "$@"
