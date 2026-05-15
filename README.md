# Quotes

A quotes API built with Python, FastAPI, and SQLite.

## Local Setup

Requirements:

- Python 3.11+
- `venv` support for your Python install
- `ensurepip` support so the repo can recover `pip` inside `.venv`

From the repository root:

```bash
./scripts/bootstrap-venv.sh
. .venv/bin/activate
uvicorn app.main:app --reload
```

`./scripts/bootstrap-venv.sh` uses `python3` by default, creates `.venv`,
repairs `pip` with `ensurepip` when the runtime allows it, and installs the
project's development dependencies.

Set `DATABASE_URL` before starting the app if you want to persist data anywhere
other than the default local SQLite file at `db.sqlite`.

The API will be available at <http://localhost:8000>.

Interactive docs: <http://localhost:8000/docs>

Planning docs for the next iterations live under `specification/`:

- `specification/roadmap.md` for phased feature and architecture work
- `specification/adr-001-eventing-strategy.md` for the eventing decision record

The service uses SQLite by default, creates its tables on startup in `db.sqlite`,
and seeds reference rates and surcharge rules used by `POST /quotes`.

## Current API Surface

- `GET /health` returns a simple readiness payload.
- `POST /quotes` validates the request, resolves a seeded schedule, applies base
  freight plus surcharge rules, persists the quote, and returns a commercial
  response with line items and a validity window derived from the matched quote
  validity policy. Set `includeAlternativeOptions=true` to include alternative
  priced options, and use optional `maxAlternativeOptions` from `1` through `10`
  to bound the number of returned alternatives.
- `POST /quotes/{quote_id}/reprice` reruns pricing for a stored quote against
  the current approved commercial data, preserves the original quote unchanged,
  and persists a structured variance summary on the repriced result.
- `POST /quotes/coverage/validate` checks whether active public tariff data
  covers a route, departure date, and equipment selection before quote creation.
- `GET /quotes/{quote_id}` returns the stored quote by either the internal UUID
  or the public `quoteReference` returned from `POST /quotes`, including the
  stored schedule snapshot, pricing basis, and pricing provenance used to
  explain the amount later.
- `GET /quotes/{quote_id}/explain` returns the persisted pricing basis,
  optimization trace, market-source details when present, and provenance used
  when the quote was created.
- `GET /quotes/reference/{quoteReference}` remains available as an explicit
  business-facing lookup path for the human-readable quote reference and
  returns the same payload as `GET /quotes/{quote_id}`.
- `GET /quotes/{quote_id}/bookability` returns whether a stored quote is still
  within its validity window and therefore usable by Booking.
- `POST /quotes/{quote_id}/approval-decisions` approves or rejects quotes that
  are currently held in the pending-approval lifecycle state and writes the
  corresponding outbox event. Requires a platform bearer token with
  `quotes:approve`.
- `GET /admin/commercial-change-events` returns the managed-commercial audit
  trail for rate-table and surcharge-rule create, update, and activate flows.
- `POST /admin/rate-tables`, `PATCH /admin/rate-tables/{rate_table_id}`, and
  `POST /admin/rate-tables/{rate_table_id}/activate` manage draft and active
  rate-table versions. Write routes require `quotes:admin`.
- `POST /admin/surcharge-rules`, `PATCH /admin/surcharge-rules/{surcharge_rule_id}`,
  and `POST /admin/surcharge-rules/{surcharge_rule_id}/activate` manage draft
  and active surcharge-rule versions. Write routes require `quotes:admin`.
- `GET /admin/outbox-events` lists durable quote and commercial outbox events
  with aggregate, event-type, publication-state, and limit filters.
- `POST /admin/outbox-consumers/{consumerName}/replay` replays an ordered batch
  of outbox events for a named downstream consumer and advances its checkpoint.
  Requires `quotes:admin`.
- `POST /admin/impact-analyses` records schedule- or contract-change impact
  summaries for affected quotes, and `GET /admin/impact-analyses/{run_id}`
  reads a recorded impact-analysis run. Creation requires `quotes:admin`.
- `POST /admin/quote-preview` lets commercial operators evaluate draft managed
  rate-table and surcharge-rule versions against a shipment before activation.
  Requires `quotes:admin`.
- `GET /admin/service-connections/equipments` checks the configured Equipments
  service `/health` endpoint and returns `ok`, `unhealthy`, or
  `not_configured` diagnostic status. Requires `quotes:admin`.
- Quote lifecycle writes also create durable rows in `outbox_events`, starting
  with `quote.created` at creation time and `quote.expired` when an issued quote
  is first observed past `validUntil`. Those payloads include the same stored
  pricing provenance snapshot used by quote reads.

### Platform Bearer Auth

Protected operational routes use the same local platform JWT shape as the
Equipments service:

- `AUTH_JWT_ISSUER`, default `platform-auth`
- `AUTH_JWT_AUDIENCE`, default `quotes-service`
- `AUTH_JWT_SECRET`, default `quotes-dev-secret` for local development
- `scope` claim with space-delimited scopes

The local development default remains `quotes-dev-secret` so tests and local
walkthroughs can mint deterministic demo tokens. Azure deployments must supply
`AUTH_JWT_SECRET` from GitHub Actions secret material and must not fall back to
the local development default.

Required scopes:

- `quotes:approve` for `POST /quotes/{quote_id}/approval-decisions`
- `quotes:admin` for managed commercial-data writes, outbox replay, impact
  analysis creation, and draft quote preview

`X-Actor` remains supported as audit metadata when a valid bearer token is
present. If `X-Actor` is omitted, the token subject is recorded as the actor.
Missing or invalid bearer tokens return `401`; valid tokens without the required
scope return `403`.

### Service Connectivity Diagnostics

`GET /admin/service-connections/equipments` is an operator diagnostic endpoint
for checking whether Quotes can reach the configured Equipments service. It is
not a business integration path and it does not accept caller-supplied target
URLs.

Configuration:

- `EQUIPMENTS_SERVICE_URL`: Equipments service base URL. If omitted or blank,
  the endpoint returns `status: "not_configured"`.
- `EQUIPMENTS_HEALTH_PATH`: health path to call, default `/health`.
- `EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS`: request timeout, default `3`, max
  `30`.

The endpoint calls the configured health URL and returns a structured payload
with the service name, configuration state, redacted base URL, health path,
HTTP status when available, and `ok: true` only for 2xx responses. Missing
bearer auth returns `401`; a valid token without `quotes:admin` returns `403`.

### Stored Pricing Provenance

- `pricingBasis` identifies which commercial mode produced the quote. The
  current implementation always stores `PUBLIC_TARIFF`.
- `pricingProvenance.referenceDataVersion` identifies the seeded tariff and
  surcharge ruleset version used for the decision. The current seed bundle is
  `seed-2026-04-01`.
- `pricingProvenance.baseRateRules` captures the exact matched base-rate rows,
  including the selected equipment type, quantity, unit amount, and effective
  validity window.
- `pricingProvenance.appliedSurchargeRules` captures the exact surcharge rules
  that contributed to the quote total, including each rule identifier,
  surcharge type, and effective qualifiers.
- `pricingProvenance.validityPolicy` captures the stored validity-policy
  snapshot used to derive `validUntil`, including the matched policy identifier,
  selection context, and any market-signal inputs.
- A known schedule can still return `400` from `POST /quotes` when the seeded
  rate table does not contain an effective row for the selected route,
  departure date, and equipment combination.

### Seeded Demo Data

The app currently boots with an in-memory schedule provider seeded with three
schedule stubs:

- `df62a7d2-a45e-4d4d-b3cb-b4af65435274` for `NLRTM -> USNYC` on `2026-08-18`
- `7a59721c-cd5d-4d9f-86a0-9aa9f7f6c47b` for `CNSHA -> DEHAM` on `2026-06-05`
- `1ce1ab21-9d58-4a6d-b867-afc93098352f` for `BRSSZ -> USLAX` on `2026-07-12`

Reference data also seeds:

- base freight rates for `20FT`, `40FT`, and `40FT_HC`
- a global BAF surcharge
- port congestion surcharges keyed by origin or destination port
- a heavy-cargo surcharge based on cargo weight per TEU
- a peak-season surcharge active from `2026-08-01` through `2026-09-30`

The seeded `BRSSZ -> USLAX` schedule is intentionally missing matching rate rows,
so it demonstrates the API's commercial validation path for unsupported quoted
lanes.

## Local Walkthrough

Use this flow when you want to verify the service locally from an operator or
integrator point of view.

### 1. Confirm the service is running

```bash
curl http://localhost:8000/health
```

Expect a `200` response before trying the quote endpoints.

### 2. Create a quote on a seeded supported lane

```bash
curl -X POST http://localhost:8000/quotes \
  -H 'Content-Type: application/json' \
  -d '{
    "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
    "equipment": [
      {"type": "20FT", "quantity": 1}
    ],
    "cargoWeightKg": 18000
  }'
```

This seeded Rotterdam to New York schedule has matching base-rate and surcharge
data, so the response should include both quote identifiers:

- `id`: internal UUID for service-to-service lookup
- `quoteReference`: human-readable `QTE-YYYY-NNNNN` reference for business flows

Keep both values from the response for the next steps.

### 3. Request bounded alternative options

```bash
curl -X POST http://localhost:8000/quotes \
  -H 'Content-Type: application/json' \
  -d '{
    "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
    "customerId": "cust-acme",
    "equipment": [
      {"type": "20FT", "quantity": 1}
    ],
    "cargoWeightKg": 18000,
    "includeAlternativeOptions": true,
    "maxAlternativeOptions": 1
  }'
```

The response includes the primary option and at most one ordered alternative.
Omitting `maxAlternativeOptions` preserves the full alternative list, while
sending it without `includeAlternativeOptions=true` keeps the normal quote
response shape.

### 4. Look up the stored quote

Internal lookup by UUID:

```bash
curl http://localhost:8000/quotes/<quote-uuid>
```

Business-facing lookup by quote reference:

```bash
curl http://localhost:8000/quotes/reference/<quote-reference>
```

The implementation also accepts the quote reference on `GET /quotes/{id}`, so
either of the following works when you already have the business identifier:

```bash
curl http://localhost:8000/quotes/<quote-reference>
curl http://localhost:8000/quotes/reference/<quote-reference>
```

All lookup paths return the stored schedule snapshot, line items, pricing basis,
and pricing provenance used to explain how the quote was calculated.

### 5. Reprice a stored quote against current approved data

```bash
curl -X POST http://localhost:8000/quotes/<quote-uuid>/reprice \
  -H 'Content-Type: application/json' \
  -d '{
    "trigger": "COMMERCIAL_REFRESH"
  }'
```

The repriced response keeps the new quote distinct from the original and
returns `varianceSummary` details for total amount, base rate, surcharges, FX,
market inputs, and optimization inputs.

### 6. Check bookability before handing the quote to Booking

```bash
curl http://localhost:8000/quotes/<quote-reference>/bookability
```

The bookability response is the Booking-oriented validity check. It returns:

- `bookable`: whether the quote can still be used
- `status`: current lifecycle state such as `ACTIVE` or `EXPIRED`
- `reason`: machine-readable explanation such as `VALIDITY_WINDOW_OPEN`
- `validUntil`: expiry timestamp from the stored quote

### 7. Exercise the unsupported-lane validation path

The seeded `BRSSZ -> USLAX` schedule is known to the service but intentionally
has no matching rate row. That makes it the easiest way to verify the commercial
validation behavior locally:

```bash
curl -X POST http://localhost:8000/quotes \
  -H 'Content-Type: application/json' \
  -d '{
    "scheduleId": "1ce1ab21-9d58-4a6d-b867-afc93098352f",
    "equipment": [
      {"type": "20FT", "quantity": 1}
    ],
    "cargoWeightKg": 18000
  }'
```

Expect a `400` response explaining that the service found the schedule but did
not find an effective commercial rate for that lane and equipment combination.

## Bruno Collection

A Bruno-compatible API collection is available under
`bruno/quotes-service/`.

- Import or open that folder directly in Bruno.
- Use the `local` environment for a local FastAPI instance.
- Use the `azure-dev` environment for the currently verified Azure App Service
  deployment.

See `bruno/quotes-service/README.md` for request details.

## Test

```bash
./scripts/verify.sh
```

That command is the canonical verification entry point for both local runs and
merge-gate automation. It bootstraps `.venv` if needed and then runs:

```bash
.venv/bin/python -m pytest tests -q
```

## CI Workflow

`.github/workflows/ci.yml` runs on pushes to `main`, pull requests targeting
`main`, and manual dispatch. It bootstraps the same repo-local `.venv` used by
local operators, validates that the project builds as a Python package, and
then executes `./scripts/verify.sh`.

## Azure Deployment

The repository includes an explicit split between infrastructure provisioning and
application deployment:

- `.github/workflows/provision-azure.yml` is a manual `workflow_dispatch`
  workflow that creates the Azure resource group, Azure Container Registry, App
  Service plan, and Linux Web App from `infra/azure/main.bicep`.
- `.github/workflows/deploy-azure.yml` runs on every push to `main` and deploys
  the application container to the existing Azure Web App. It can also be run
  manually with `workflow_dispatch`. If the Azure infrastructure has not been
  provisioned yet, it exits without failing the run.

The deployment target is a containerized Linux App Service. The app persists its
SQLite database at `/home/site/data/quotes.db`, which uses App Service's
persistent storage.

The application `Dockerfile` uses an MCR-hosted Python 3.11 base image so the
remote `az acr build` step does not depend on unauthenticated Docker Hub pulls.

### GitHub Configuration

Create these GitHub Actions secrets before running the provisioning workflow:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AUTH_JWT_SECRET`

These are used with GitHub Actions OIDC via `azure/login`. The backing Azure
service principal needs permission to create and update the target resource
group and resources.

`AUTH_JWT_SECRET` is the HS256 signing secret accepted by the deployed Quotes
App Service for protected operational routes. Store it only in GitHub Actions
secrets or an equivalent secret manager; never commit the secret value.

Optional GitHub Actions variables:

- `AZURE_ENV_NAME`: defaults to `prod`
- `AZURE_LOCATION`: defaults to `eastus`
- `AUTH_JWT_ISSUER`: defaults to `platform-auth`
- `EQUIPMENTS_SERVICE_URL`: optional Equipments service base URL for
  `GET /admin/service-connections/equipments`; leave unset until the live
  Equipments URL is known.
- `EQUIPMENTS_HEALTH_PATH`: defaults to `/health`
- `EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS`: defaults to `3`
- `RUNNER_LABELS_JSON`: defaults to `["ubuntu-latest"]`; set to a JSON array
  such as `["self-hosted", "linux", "x64"]` to run the workflows on a
  self-hosted runner

`AUTH_JWT_AUDIENCE` is fixed to `quotes-service` by the Azure workflows so the
deployed service matches the documented Quotes audience contract.

Resource names are derived automatically from the repository name, environment
name, and subscription ID, so no extra naming variables are required.

Both Azure workflows try to use an existing `az` installation first and only
fall back to installing the Azure CLI on the runner when it is missing.

### Platform Auth Secret Rotation

Rotate the platform auth secret by updating the `AUTH_JWT_SECRET` GitHub
Actions secret, then rerun `Deploy to Azure`. The deploy workflow reapplies
`AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE=quotes-service`, and `AUTH_JWT_SECRET` to
the existing App Service before restarting it. Rerun `Provision Azure
Infrastructure` only when rebuilding or recreating the Azure resources.

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
│   ├── main.py          # app/main.py: ASGI entry point, routes, pricing flow
│   ├── models.py        # Quote, rate, and surcharge models
│   ├── seed.py          # Reference rate and surcharge seed data
│   ├── schedules.py     # app/schedules.py: seeded schedule provider
│   └── surcharges.py    # Surcharge matching and calculation logic
├── scripts/
│   ├── bootstrap-venv.sh # Local virtualenv bootstrap
│   └── verify.sh        # scripts/verify.sh: pytest verification wrapper
├── specification/
│   ├── quotes.md        # specification/quotes.md: API and behavior spec
│   ├── quote-scenarios.md # specification/quote-scenarios.md: scenario catalog
│   ├── roadmap.md       # Delivery roadmap
│   └── system-architecture.md # Current service architecture notes
├── tests/
│   ├── __init__.py
│   ├── test_db.py       # SQLite model coverage
│   ├── test_documentation.py # Documentation/API-surface checks
│   ├── test_health.py   # Health endpoint smoke tests
│   ├── test_quotes_api.py # Quote creation and retrieval coverage
│   ├── test_seed.py     # tests/test_seed.py: seed-data coverage
│   └── test_surcharges.py # Surcharge rule behavior coverage
├── bruno/quotes-service/ # Bruno API collection for manual checks
├── pyproject.toml     # Project metadata and dependencies
└── README.md
```
