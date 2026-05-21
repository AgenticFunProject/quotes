#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_PATH = REPO_ROOT / "specification" / "quote-scenarios.md"
TESTS_DIR = REPO_ROOT / "tests"
SCENARIO_PREFIX = "## Scenario: "
MATRIX_HEADING = "Contract Coverage Matrix"
FORBIDDEN_SCENARIO_TERMS = [
    "architecture-state",
    "broader architecture state",
    "repository landscape",
    "town workspace",
    "unverified responsibilities",
    "assumptions or gaps",
    "documentation expectations",
]


def section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.find(marker)
    if start == -1:
        raise ValueError(f"missing section: {heading}")
    next_heading = markdown.find("\n## ", start + len(marker))
    if next_heading == -1:
        return markdown[start:]
    return markdown[start:next_heading]


def scenario_headings(markdown: str) -> list[str]:
    return [line.removeprefix(SCENARIO_PREFIX) for line in markdown.splitlines() if line.startswith(SCENARIO_PREFIX)]


def scenario_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for heading in scenario_headings(markdown):
        marker = f"{SCENARIO_PREFIX}{heading}"
        start = markdown.index(marker)
        next_heading = markdown.find(f"\n{SCENARIO_PREFIX}", start + len(marker))
        sections[heading] = markdown[start:] if next_heading == -1 else markdown[start:next_heading]
    return sections


def contract_coverage_matrix(markdown: str) -> dict[str, list[str]]:
    matrix: dict[str, list[str]] = {}
    matrix_section = section(markdown, MATRIX_HEADING)
    for line in matrix_section.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] == "Scenario" or set(cells[0]) == {"-"}:
            continue
        refs = [ref.strip().strip("`") for ref in cells[1].split("<br>") if ref.strip()]
        matrix[cells[0]] = refs
    return matrix


def test_functions_by_file() -> dict[str, set[str]]:
    tests_by_file: dict[str, set[str]] = {}
    for path in TESTS_DIR.glob("test_*.py"):
        contents = path.read_text()
        tests_by_file[f"tests/{path.name}"] = set(re.findall(r"^def (test_[a-zA-Z0-9_]+)\(", contents, re.MULTILINE))
    return tests_by_file


def validate() -> list[str]:
    errors: list[str] = []
    markdown = SCENARIOS_PATH.read_text()

    scenarios = scenario_headings(markdown)
    if not scenarios:
        errors.append("no scenario headings found")

    try:
        coverage = contract_coverage_matrix(markdown)
    except ValueError as error:
        errors.append(str(error))
        coverage = {}

    if list(coverage) != scenarios:
        errors.append("contract coverage matrix must match scenario headings exactly and in order")
        missing = [scenario for scenario in scenarios if scenario not in coverage]
        extra = [scenario for scenario in coverage if scenario not in scenarios]
        if missing:
            errors.append(f"missing matrix rows: {', '.join(missing)}")
        if extra:
            errors.append(f"extra matrix rows: {', '.join(extra)}")

    tests_by_file = test_functions_by_file()
    for scenario_name, refs in coverage.items():
        if not refs:
            errors.append(f"{scenario_name}: no executable coverage references")
            continue
        for ref in refs:
            file_name, separator, test_name = ref.partition("::")
            if separator != "::":
                errors.append(f"{scenario_name}: malformed coverage reference: {ref}")
                continue
            if file_name not in tests_by_file:
                errors.append(f"{scenario_name}: missing test file: {file_name}")
                continue
            if test_name not in tests_by_file[file_name]:
                errors.append(f"{scenario_name}: missing test function: {ref}")

    for scenario_name, scenario in scenario_sections(markdown).items():
        if "\nGiven " not in scenario:
            errors.append(f"{scenario_name}: missing Given step")
        if "\nWhen " not in scenario:
            errors.append(f"{scenario_name}: missing When step")
        if "\nThen " not in scenario:
            errors.append(f"{scenario_name}: missing Then step")
        for forbidden_term in FORBIDDEN_SCENARIO_TERMS:
            if forbidden_term in scenario:
                errors.append(f"{scenario_name}: forbidden term: {forbidden_term}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"gherkin-contract: {error}", file=sys.stderr)
        return 1

    scenario_count = len(scenario_headings(SCENARIOS_PATH.read_text()))
    print(f"gherkin-contract: verified {scenario_count} scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
