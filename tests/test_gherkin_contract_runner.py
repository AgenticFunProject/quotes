from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from gherkin_contract import _assert_responses  # noqa: E402

RUNNER = REPO_ROOT / "scripts" / "gherkin_contract.py"
SPEC = REPO_ROOT / "specification" / "quote-scenarios.md"
BINDINGS = REPO_ROOT / "specification" / "gherkin-bindings.yaml"

SMOKE_SCENARIOS = [
    "Create a quote on a seeded peak-season lane",
    "Retrieve a stored quote",
    "Validate whether a stored quote can still be booked",
    "Revoke an issued quote and block booking reuse",
]
PUBLIC_LIFECYCLE_SCENARIOS = [
    "Validate rate coverage before requesting a quote",
    "Plan equipment availability with explicit substitution suggestions",
    "Persist quote lifecycle events in the outbox",
    "Request a quote for a seeded schedule without an effective rate",
    "Reprice an existing quote and explain the commercial variance",
    "Return multiple commercial options for one quote request",
    "Bound alternative options on quote creation",
]
EXECUTABLE_SCENARIOS = [*SMOKE_SCENARIOS, *PUBLIC_LIFECYCLE_SCENARIOS]


def _run_contract_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_contract_runner_has_no_service_or_pytest_imports() -> None:
    tree = ast.parse(RUNNER.read_text())
    forbidden_roots = {"app", "db", "seed", "tests", "pytest"}
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", maxsplit=1)[0])

    assert imports.isdisjoint(forbidden_roots)


def test_contract_cli_lists_scenarios_from_markdown() -> None:
    result = _run_contract_command("list", "--spec", str(SPEC), "--bindings", str(BINDINGS))

    assert result.returncode == 0, result.stderr
    for scenario in SMOKE_SCENARIOS:
        assert scenario in result.stdout
    assert "41 scenarios" in result.stdout


def test_contract_cli_validates_binding_coverage() -> None:
    result = _run_contract_command("validate", "--spec", str(SPEC), "--bindings", str(BINDINGS))

    assert result.returncode == 0, result.stderr
    assert "gherkin-contract: verified 41 scenarios" in result.stdout
    assert "11 executable bindings" in result.stdout
    for scenario in EXECUTABLE_SCENARIOS:
        assert scenario in result.stdout


def test_contract_cli_dry_runs_smoke_group_without_service() -> None:
    result = _run_contract_command(
        "run",
        "--spec",
        str(SPEC),
        "--bindings",
        str(BINDINGS),
        "--profile",
        "local",
        "--group",
        "smoke",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "dry-run: local smoke" in result.stdout
    for scenario in SMOKE_SCENARIOS:
        assert f"DRY-RUN {scenario}" in result.stdout


def test_smoke_bindings_define_profiles_fixtures_actions_and_assertions() -> None:
    document = yaml.safe_load(BINDINGS.read_text())
    scenarios = document["scenarios"]

    for scenario in SMOKE_SCENARIOS:
        binding = scenarios[scenario]
        assert binding["group"] == "smoke"
        assert "local" in binding["profiles"]
        assert binding["fixtures"]
        assert binding["actions"]
        assert binding["assertions"]


def test_public_lifecycle_bindings_define_executable_black_box_steps() -> None:
    document = yaml.safe_load(BINDINGS.read_text())
    scenarios = document["scenarios"]

    for scenario in PUBLIC_LIFECYCLE_SCENARIOS:
        binding = scenarios[scenario]
        assert binding["status"] == "executable"
        assert "local" in binding["profiles"]
        assert binding["fixtures"]
        assert binding["actions"]
        assert binding["assertions"]


def test_public_lifecycle_bindings_dry_run_without_service() -> None:
    for scenario in PUBLIC_LIFECYCLE_SCENARIOS:
        result = _run_contract_command(
            "run",
            "--spec",
            str(SPEC),
            "--bindings",
            str(BINDINGS),
            "--profile",
            "local",
            "--scenario",
            scenario,
            "--dry-run",
        )

        assert result.returncode == 0, result.stderr
        assert f"DRY-RUN {scenario}" in result.stdout


def test_smoke_create_quote_assertions_match_created_response() -> None:
    document = yaml.safe_load(BINDINGS.read_text())
    scenarios = document["scenarios"]

    for scenario in SMOKE_SCENARIOS:
        binding = scenarios[scenario]
        create_quote_status_assertions = [
            assertion
            for assertion in binding["assertions"]
            if assertion.get("action") == "create_quote" and "status" in assertion
        ]

        assert create_quote_status_assertions == [{"action": "create_quote", "status": 201}]


def test_create_quote_smoke_binding_asserts_creation_response_fields_only() -> None:
    document = yaml.safe_load(BINDINGS.read_text())
    binding = document["scenarios"]["Create a quote on a seeded peak-season lane"]

    create_quote_fields = [
        assertion["json_field"]
        for assertion in binding["assertions"]
        if assertion.get("action") == "create_quote" and "json_field" in assertion
    ]

    assert create_quote_fields == ["$.id", "$.quoteReference"]


def test_contract_assertions_can_check_nested_option_lists_and_missing_fields() -> None:
    _assert_responses(
        "Bound alternative options on quote creation",
        [
            {
                "action": "create_quote",
                "path": "$.options.alternatives.0.pricingBasis",
                "json_equals": "PUBLIC_TARIFF",
            },
            {
                "action": "create_quote",
                "json_missing": "$.options.alternatives.1",
            },
            {
                "action": "create_quote",
                "json_missing": "$.options.unused",
            },
        ],
        {
            "create_quote": (
                201,
                {
                    "options": {
                        "alternatives": [
                            {
                                "pricingBasis": "PUBLIC_TARIFF",
                            }
                        ]
                    }
                },
            )
        },
    )
