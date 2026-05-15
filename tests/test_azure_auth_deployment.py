from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_bicep_provisions_platform_auth_app_settings_without_local_secret() -> None:
    template = _read("infra/azure/main.bicep")

    assert "param authJwtIssuer string = 'platform-auth'" in template
    assert "param authJwtAudience string = 'quotes-service'" in template
    assert "@secure()" in template
    assert "param authJwtSecret string" in template

    for setting_name in [
        "AUTH_JWT_ISSUER",
        "AUTH_JWT_AUDIENCE",
        "AUTH_JWT_SECRET",
    ]:
        assert f"name: '{setting_name}'" in template

    assert "value: authJwtIssuer" in template
    assert "value: authJwtAudience" in template
    assert "value: authJwtSecret" in template
    assert "quotes-dev-secret" not in template


def test_bicep_provisions_equipments_connectivity_diagnostic_settings() -> None:
    template = _read("infra/azure/main.bicep")

    assert "param equipmentsServiceUrl string = ''" in template
    assert "param equipmentsHealthPath string = '/health'" in template
    assert "param equipmentsConnectivityTimeoutSeconds string = '3'" in template

    for setting_name in [
        "EQUIPMENTS_SERVICE_URL",
        "EQUIPMENTS_HEALTH_PATH",
        "EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS",
    ]:
        assert f"name: '{setting_name}'" in template

    assert "value: equipmentsServiceUrl" in template
    assert "value: equipmentsHealthPath" in template
    assert "value: equipmentsConnectivityTimeoutSeconds" in template


def test_azure_workflows_supply_platform_auth_from_github_secret_material() -> None:
    provision = _read(".github/workflows/provision-azure.yml")
    deploy = _read(".github/workflows/deploy-azure.yml")

    for workflow in [provision, deploy]:
        assert "AUTH_JWT_ISSUER: ${{ vars.AUTH_JWT_ISSUER || 'platform-auth' }}" in workflow
        assert "AUTH_JWT_AUDIENCE: quotes-service" in workflow
        assert "AUTH_JWT_SECRET: ${{ secrets.AUTH_JWT_SECRET }}" in workflow
        assert "quotes-dev-secret" not in workflow

    assert 'authJwtIssuer="$AUTH_JWT_ISSUER"' in provision
    assert 'authJwtAudience="$AUTH_JWT_AUDIENCE"' in provision
    assert 'authJwtSecret="$AUTH_JWT_SECRET"' in provision

    assert "az webapp config appsettings set" in deploy
    for setting_name in [
        "AUTH_JWT_ISSUER",
        "AUTH_JWT_AUDIENCE",
        "AUTH_JWT_SECRET",
    ]:
        assert f'{setting_name}="$' in deploy
    assert "--output none" in deploy


def test_azure_workflows_supply_equipments_connectivity_settings_from_variables() -> None:
    provision = _read(".github/workflows/provision-azure.yml")
    deploy = _read(".github/workflows/deploy-azure.yml")

    for workflow in [provision, deploy]:
        assert "EQUIPMENTS_SERVICE_URL: ${{ vars.EQUIPMENTS_SERVICE_URL || '' }}" in workflow
        assert "EQUIPMENTS_HEALTH_PATH: ${{ vars.EQUIPMENTS_HEALTH_PATH || '/health' }}" in workflow
        assert "EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS: ${{ vars.EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS || '3' }}" in workflow

    assert 'equipmentsServiceUrl="$EQUIPMENTS_SERVICE_URL"' in provision
    assert 'equipmentsHealthPath="$EQUIPMENTS_HEALTH_PATH"' in provision
    assert 'equipmentsConnectivityTimeoutSeconds="$EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS"' in provision

    for setting_name in [
        "EQUIPMENTS_SERVICE_URL",
        "EQUIPMENTS_HEALTH_PATH",
        "EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS",
    ]:
        assert f'{setting_name}="$' in deploy


def test_readme_documents_azure_auth_secret_rotation_and_local_defaults() -> None:
    readme = _read("README.md")

    assert "AUTH_JWT_SECRET" in readme
    assert "EQUIPMENTS_SERVICE_URL" in readme
    assert "The local development default remains `quotes-dev-secret`" in readme
    assert "Rotate the platform auth secret" in readme
    assert "rerun `Deploy to Azure`" in readme
    assert "never commit the secret value" in readme
