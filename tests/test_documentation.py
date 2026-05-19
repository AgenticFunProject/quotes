from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.index(marker)
    next_heading = markdown.find("\n## ", start + len(marker))
    if next_heading == -1:
        return markdown[start:]
    return markdown[start:next_heading]


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
        "specification/quotes.md",
        "specification/quote-scenarios.md",
    ]:
        assert path in project_structure


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


def test_specs_accept_stable_quote_option_identifiers_for_booking() -> None:
    spec = (REPO_ROOT / "specification" / "quotes.md").read_text()
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    for text in [spec, scenarios]:
        assert "quoteOptionId" in text
        assert "GET /quotes/{id}?optionId={quoteOptionId}" in text
        assert "GET /quotes/{id}/bookability?optionId={quoteOptionId}" in text

    assert "one aggregate quote record with child option records" in spec
    assert "Stable Booking-facing option identifiers remain future work" not in spec
    assert "Select the primary quote option by stable identifier" in scenarios
    assert "Select an alternative quote option by stable identifier" in scenarios
    assert "Reject an expired or unavailable quote option" in scenarios


def test_specs_document_platform_bearer_auth_for_protected_operations() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    spec = (REPO_ROOT / "specification" / "quotes.md").read_text()
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    for text in [readme, spec, scenarios]:
        assert "quotes:admin" in text
        assert "quotes:approve" in text
        assert "`role=admin`" in text

    assert "AUTH_JWT_AUDIENCE" in spec
    assert "quotes-service" in spec
    assert "Require platform bearer authorization for commercial admin changes" in scenarios
    assert "Require platform bearer authorization for quote approval decisions" in scenarios
    assert "without the required Quotes scope" in readme


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
        "Quotes keeps scope-only authorization",
        "`role=admin` alone does not authorize protected Quotes operations",
        "return `401`",
        "return `403`",
        "`/api/auth/quotes-token`",
        "must not attach bearer tokens to public quote request or read calls",
        "Deploy to Azure",
        "Booking and Equipments integration boundaries",
        "Remaining open decisions",
    ]:
        assert text in plan

    assert "`role=admin` compatibility remains an open decision" not in plan
    assert "Whether Quotes should accept `role=admin`" not in plan


def test_quote_scenarios_cover_2026_05_19_auth_rbac_deployment_boundaries() -> None:
    scenarios = (REPO_ROOT / "specification" / "quote-scenarios.md").read_text()

    for scenario_name in [
        "Accept Users-issued Quotes-audience platform tokens for protected operations",
        "Accept gateway-issued Quotes-audience platform tokens for protected operations",
        "Reject missing or invalid protected-route bearer tokens",
        "Reject valid tokens without the required Quotes scope",
        "Reject role=admin without the required Quotes scope",
        "Keep web-page bearer propagation inside the gateway boundary",
        "Verify Azure platform auth settings before deployment sign-off",
        "Keep Booking on public quote validation and Equipments on diagnostics",
    ]:
        assert f"## Scenario: {scenario_name}" in scenarios
