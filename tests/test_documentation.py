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
