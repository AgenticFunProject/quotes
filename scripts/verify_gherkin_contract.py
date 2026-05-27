#!/usr/bin/env python3
from __future__ import annotations

import sys

from gherkin_contract import (
    DEFAULT_BINDINGS_PATH,
    DEFAULT_FEATURES_PATH,
    load_contract,
    print_validation_summary,
    validate_contract,
)


def main() -> int:
    contract = load_contract(DEFAULT_FEATURES_PATH, DEFAULT_BINDINGS_PATH)
    errors = validate_contract(contract)
    if errors:
        for error in errors:
            print(f"gherkin-contract: {error}", file=sys.stderr)
        return 1

    print_validation_summary(contract)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
