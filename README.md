# Quotes

A quotes API built with Python, FastAPI, and SQLite.

## Requirements

- Python 3.11+

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn app.main:app --reload
```

The API will be available at <http://localhost:8000>.

Interactive docs: <http://localhost:8000/docs>

The service uses SQLite by default, creates its tables on startup in `db.sqlite`,
and seeds reference rates and surcharge rules used by `POST /quotes`.

## Run Locally on Linux

Prerequisites:

- Python 3.11+
- `venv` support for your Python install
- `pip`

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

If your Linux distribution does not expose `python`, use `python3` in the
commands above instead.

## Example

```bash
curl -X POST http://localhost:8000/quotes \
  -H 'Content-Type: application/json' \
  -d '{
    "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
    "equipment": [{"type": "20FT", "quantity": 1}],
    "cargoWeightKg": 18000
  }'
```

## Bruno Collection

A Bruno-compatible API collection is available under
`bruno/quotes-service/`.

- Import or open that folder directly in Bruno.
- Use the `local` environment for a local FastAPI instance.
- Use the `azure-dev` environment for the currently verified Azure App Service
  deployment.

See `bruno/quotes-service/README.md` for request details and the current
`GET /quotes/{id}` limitation.

## Test

```bash
pytest
```

## Azure Deployment

The repository includes an explicit split between infrastructure provisioning and
application deployment:

- `.github/workflows/provision-azure.yml` is a manual `workflow_dispatch`
  workflow that creates the Azure resource group, Azure Container Registry, App
  Service plan, and Linux Web App from `infra/azure/main.bicep`.
- `.github/workflows/deploy-azure.yml` runs on every push to `main` and deploys
  the application container to the existing Azure Web App. If the Azure
  infrastructure has not been provisioned yet, it exits without failing the run.

The deployment target is a containerized Linux App Service. The app persists its
SQLite database at `/home/site/data/quotes.db`, which uses App Service's
persistent storage.

### GitHub Configuration

Create these GitHub Actions secrets before running the provisioning workflow:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

These are used with GitHub Actions OIDC via `azure/login`. The backing Azure
service principal needs permission to create and update the target resource
group and resources.

Optional GitHub Actions variables:

- `AZURE_ENV_NAME`: defaults to `prod`
- `AZURE_LOCATION`: defaults to `eastus`
- `RUNNER_LABELS_JSON`: defaults to `["ubuntu-latest"]`; set to a JSON array
  such as `["self-hosted", "linux", "x64"]` to run the workflows on a
  self-hosted runner

Resource names are derived automatically from the repository name, environment
name, and subscription ID, so no extra naming variables are required.

### Provisioning Flow

1. Configure the Azure OIDC secrets and optional variables.
2. Run `Provision Azure Infrastructure` from the GitHub Actions UI.
3. After the workflow completes, merge or push to `main` to trigger the first
   application deployment.

### Local Agent MCP Setup

`opencode.json` wires in project-local MCP entries for Azure and GitHub:

- `azure` uses the official `@azure/mcp` package through `npx`
- `github` uses GitHub's remote MCP endpoint

For local use:

- Authenticate Azure with `az login`
- Authenticate GitHub MCP with `opencode mcp auth github`

Both integrations are now available to OpenCode-based local agents in this
repository.

## Project Structure

```
quotes/
├── app/
│   ├── __init__.py      # FastAPI app instance + startup hooks
│   ├── db.py            # SQLAlchemy engine and session helpers
│   ├── main.py          # ASGI entry point
│   └── models.py        # Quote, rate, and surcharge models
├── tests/
│   ├── __init__.py
│   ├── test_db.py       # SQLite model coverage
│   └── test_health.py   # Smoke tests
├── pyproject.toml     # Project metadata and dependencies
└── README.md
```
