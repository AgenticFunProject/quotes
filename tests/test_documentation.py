from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PREFIX = "## Scenario: "


EXPECTED_QUOTE_SCENARIOS = [
    "Create a quote on a seeded peak-season lane",
    "Retrieve a stored quote",
    "Validate whether a stored quote can still be booked",
    "Validate rate coverage before requesting a quote",
    "Persist quote lifecycle events in the outbox",
    "Request a quote for a seeded schedule without an effective rate",
    "Apply customer contract pricing with surcharge waivers",
    "Prefer account contract pricing over customer pricing",
    "Create, update, and activate a managed rate-table version",
    "Create, update, and activate a managed surcharge-rule version",
    "Require platform bearer authorization for commercial admin changes",
    "Require platform bearer authorization for quote approval decisions",
    "Check Equipments service connectivity",
    "Record an audit trail for managed commercial changes",
    "Publish managed commercial changes to the outbox",
    "Replay outbox events for a named downstream consumer",
    "Analyze quote impact for schedule or contract changes",
    "Preview quote pricing with draft managed commercial data",
    "Return a quote in a requested display currency",
    "Use approved market pricing when the client hints MARKET",
    "Fall back from MARKET to contract or tariff pricing when market coverage is missing",
    "Explain why a quote used market or fallback pricing",
    "Reprice an existing quote and explain the commercial variance",
    "Return multiple commercial options for one quote request",
    "Bound alternative options on quote creation",
    "Hold a quote for manual approval when commercial guardrails are exceeded",
    "Approve a previously held quote without changing the reviewed commercial snapshot",
    "Reject a previously held quote and preserve the review trail",
    "Derive quote validity from a customer-specific policy",
    "Derive shorter quote validity from high-volatility market pricing",
    "Explain why similar quotes received different validity windows",
    "Accept Users-issued Quotes-audience platform tokens for protected operations",
    "Accept gateway-issued Quotes-audience platform tokens for protected operations",
    "Reject missing or invalid protected-route bearer tokens",
    "Reject valid tokens without the required Quotes scope",
    "Resolve role=admin compatibility before implementation",
    "Keep web-page bearer propagation inside the gateway boundary",
    "Verify Azure platform auth settings before deployment sign-off",
    "Keep Booking on public quote validation and Equipments on diagnostics",
]

FORBIDDEN_SCENARIO_TERMS = [
    "architecture-state",
    "broader architecture state",
    "repository landscape",
    "town workspace",
    "unverified responsibilities",
    "assumptions or gaps",
    "documentation expectations",
]


def _section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.index(marker)
    next_heading = markdown.find("\n## ", start + len(marker))
    if next_heading == -1:
        return markdown[start:]
    return markdown[start:next_heading]


def _scenario_headings(markdown: str) -> list[str]:
    return [line.removeprefix(SCENARIO_PREFIX) for line in markdown.splitlines() if line.startswith(SCENARIO_PREFIX)]


def _scenario_sections(markdown: str) -> dict[str, str]:
    sections = {}
    for heading in _scenario_headings(markdown):
        marker = f"{SCENARIO_PREFIX}{heading}"
        start = markdown.index(marker)
        next_heading = markdown.find(f"\n{SCENARIO_PREFIX}", start + len(marker))
        sections[heading] = markdown[start:] if next_heading == -1 else markdown[start:next_heading]
    return sections


def _contract_coverage_matrix(markdown: str) -> dict[str, list[str]]:
    matrix = {}
    section = _section(markdown, "Contract Coverage Matrix")
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] == "Scenario" or set(cells[0]) == {"-"}:
            continue
        refs = [ref.strip().strip("`") for ref in cells[1].split("<br>") if ref.strip()]
        matrix[cells[0]] = refs
    return matrix


def _test_functions_by_file() -> dict[str, set[str]]:
    tests_by_file = {}
    for path in (REPO_ROOT / "tests").glob("test_*.py"):
        contents = path.read_text()
        tests_by_file[f"tests/{path.name}"] = set(re.findall(r"^def (test_[a-zA-Z0-9_]+)\(", contents, re.MULTILINE))
    return tests_by_file


def test_readme_current_api_surface_lists_implemented_support_endpoints() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    api_surface = _section(readme, "Current API Surface")

    for endpoint in [
        "POST /quotes/coverage/validate",
        "GET /quotes/{quote_id}/explain",
        "POST /quotes/{quote_id}/approval-decisions",
        "GET /admin/outbox-events",
        "POST /admin/outbox-consumers/{consumerName}/replay",
        "POST /admin/impact-analyses",
    ]:
        assert endpoint in api_surface


def test_readme_project_structure_mentions_current_modules_and_tests() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    project_structure = _section(readme, "Project Structure")

    for path in [
        "app/schedules.py",
        "tests/test_seed.py",
        "scripts/verify.sh",
        "scripts/verify_gherkin_contract.py",
        "specification/quotes.md",
        "specification/quote-scenarios.md",
    ]:
        assert path in project_structure


def test_ci_runs_standalone_gherkin_contract_verifier() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    verify_script = (REPO_ROOT / "scripts" / "verify.sh").read_text()

    assert "Verify Gherkin contract coverage" in workflow
    assert "scripts/verify_gherkin_contract.py" in workflow
    assert "scripts/verify_gherkin_contract.py" in verify_script


def test_spec_endpoint_table_includes_current_workflow_routes() -> None:
    spec = (REPO_ROOT / "specification" / "quotes.md").read_text()
    endpoints = _section(spec, "API Endpoints")

    for path in [
        "/quotes/{id}/approval-decisions",
        "/admin/service-connections/equipments",
        "/admin/outbox-events",
        "/admin/outbox-consumers/{consumerName}/replay",
        "/admin/impact-analyses",
        "/admin/impact-analyses/{id}",
    ]:
        assert path in endpoints


def test_specs_document_bounded_alternative_options_as_current_behavior() -> None:
    spec = (REPO_ROOT / "specification" / "quotes.md").read_text()
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    assert "includeAlternativeOptions" in spec
    assert "maxAlternativeOptions" in spec
    assert "accepts values from `1` through `10`" in spec
    assert "Bound alternative options on quote creation" in scenarios


def test_specs_document_platform_bearer_auth_for_protected_operations() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    spec = (REPO_ROOT / "specification" / "quotes.md").read_text()
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    for text in [readme, spec, scenarios]:
        assert "quotes:admin" in text
        assert "quotes:approve" in text

    assert "AUTH_JWT_AUDIENCE" in spec
    assert "quotes-service" in spec
    assert "Require platform bearer authorization for commercial admin changes" in scenarios
    assert "Require platform bearer authorization for quote approval decisions" in scenarios


def test_specs_document_equipments_connectivity_diagnostic() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    spec = (REPO_ROOT / "specification" / "quotes.md").read_text()
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    for text in [readme, spec, scenarios]:
        assert "/admin/service-connections/equipments" in text
        assert "EQUIPMENTS_SERVICE_URL" in text
        assert "quotes:admin" in text

    assert "not_configured" in spec
    assert "unhealthy" in spec
    assert "Check Equipments service connectivity" in scenarios


def test_system_architecture_documents_current_repositories_and_azure_deployment() -> None:
    architecture = (REPO_ROOT / "specification" / "system-architecture.md").read_text()

    for repo in ["`quotes`", "`booking`", "`equipments`", "`web-page`", "`users`"]:
        assert repo in architecture

    assert "app-quotes-dev-371ad1" in architecture
    assert "rg-quotes-dev-371ad1" in architecture
    assert "No deployed Azure resources were confirmed" in architecture
    assert "`web-page`, or `users`" in architecture


def test_system_architecture_documents_2026_05_19_auth_and_deployment_evidence() -> None:
    architecture = (REPO_ROOT / "specification" / "system-architecture.md").read_text()
    evidence = _section(architecture, "2026-05-19 Auth And Deployment Evidence Snapshot")

    for text in [
        "Users: confirmed local SQLite user records",
        "Bearer-token enforcement remains out of scope",
        "Equipments: confirmed HS256 bearer-token enforcement",
        "`equipments:read`",
        "`equipments:modify`",
        "web-page: confirmed `/api/auth/quotes-token` helper",
        "browser API helper currently attaches bearer tokens only to `/api/equipment`",
        "Booking: local working tree state may vary by active branch",
        "`origin/master` confirms Spring Boot source and tests",
        "QuoteClientRestClient must not forward the caller `Authorization` header",
        "Quotes Azure deployment: confirmed workflow wiring",
        "`AUTH_JWT_AUDIENCE=quotes-service`",
        "Gap:",
        "Assumption:",
    ]:
        assert text in evidence

    assert "Booking: confirmed specification-only repository state" not in evidence


def test_quotes_spec_contains_2026_05_19_auth_rbac_deployment_plan() -> None:
    spec = (REPO_ROOT / "specification" / "quotes.md").read_text()
    plan = _section(spec, "2026-05-19 Cross-Repo Auth/RBAC Deployment Plan")

    for text in [
        "Token issuer, audience, and source",
        "`AUTH_JWT_ISSUER`",
        "`AUTH_JWT_AUDIENCE`",
        "`AUTH_JWT_SECRET`",
        "`quotes-service`",
        "Users-issued or gateway-issued Quotes-audience tokens",
        "`quotes:admin`",
        "`quotes:approve`",
        "`role=admin` compatibility remains an open decision",
        "return `401`",
        "return `403`",
        "`/api/auth/quotes-token`",
        "must not attach bearer tokens to public quote request or read calls",
        "Deploy to Azure",
        "Booking and Equipments integration boundaries",
        "Remaining open decisions",
    ]:
        assert text in plan


def test_quote_scenarios_cover_2026_05_19_auth_rbac_deployment_boundaries() -> None:
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    for scenario_name in [
        "Accept Users-issued Quotes-audience platform tokens for protected operations",
        "Accept gateway-issued Quotes-audience platform tokens for protected operations",
        "Reject missing or invalid protected-route bearer tokens",
        "Reject valid tokens without the required Quotes scope",
        "Resolve role=admin compatibility before implementation",
        "Keep web-page bearer propagation inside the gateway boundary",
        "Verify Azure platform auth settings before deployment sign-off",
        "Keep Booking on public quote validation and Equipments on diagnostics",
    ]:
        assert f"## Scenario: {scenario_name}" in scenarios


def test_quote_scenario_catalog_contains_only_quote_behavior_scenarios() -> None:
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    assert _scenario_headings(scenarios) == EXPECTED_QUOTE_SCENARIOS


def test_quote_scenario_catalog_has_executable_contract_coverage_matrix() -> None:
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()
    coverage = _contract_coverage_matrix(scenarios)
    tests_by_file = _test_functions_by_file()

    assert list(coverage) == EXPECTED_QUOTE_SCENARIOS
    for scenario_name, refs in coverage.items():
        assert refs, scenario_name
        for ref in refs:
            file_name, separator, test_name = ref.partition("::")
            assert separator == "::", f"{scenario_name}: {ref}"
            assert file_name in tests_by_file, f"{scenario_name}: {ref}"
            assert test_name in tests_by_file[file_name], f"{scenario_name}: {ref}"


def test_quote_scenario_sections_have_concrete_gherkin_shape() -> None:
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    for scenario_name, scenario in _scenario_sections(scenarios).items():
        assert "\nGiven " in scenario, scenario_name
        assert "\nWhen " in scenario, scenario_name
        assert "\nThen " in scenario, scenario_name
        for forbidden_term in FORBIDDEN_SCENARIO_TERMS:
            assert forbidden_term not in scenario, scenario_name


def test_quotes_spec_keeps_scenario_catalog_focused_on_quote_behavior() -> None:
    spec = (REPO_ROOT / "specification" / "quotes.md").read_text()
    executable_scenarios = _section(spec, "Executable Scenarios")

    assert "quote service behavior and documented integration boundaries" in executable_scenarios
    assert "architecture-state scenarios" not in executable_scenarios
