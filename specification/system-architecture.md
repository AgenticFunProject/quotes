# System Architecture State

## Purpose

This document records the current system-level repository and workspace state around the Quotes service.

It complements `specification/quotes.md`, which defines the service contract, by documenting the broader repository landscape, control-plane boundaries, integration assumptions, and known gaps that exist today.

## Maintenance Rules

- Treat this document as a maintained snapshot of confirmed architecture state, not a speculative target design.
- Prefer evidence visible in the current workspace, repository contents, and committed documentation.
- Mark anything not directly confirmed here as an assumption or gap.
- Update this document whenever a repository is added, removed, renamed, or given a new responsibility that changes system boundaries.

## State Legend

- Confirmed: directly supported by the current workspace, repository contents, or committed documentation.
- Assumption: likely true from naming or surrounding context, but not fully specified in this repository.
- Gap: an integration or ownership boundary that is visible but not yet documented well enough.

## Current Workspace Topology

Confirmed paths visible from the current AgenticFunProject workspace:

- City root: `/home/user/projects/gascity/examples/agenticfun`
- Service repositories: `/home/user/projects/gascity/examples/agenticfun/repos/*`
- Quotes repository: `/home/user/projects/gascity/examples/agenticfun/repos/quotes`
- Rig runtime state: per-rig `.beads/`, `.gc/`, and `.codex/` directories

That distinction matters:

- Service code and service documentation changes belong in the service git repository.
- Rig runtime and orchestration directories are local control-plane state, not application source.
- The `booking`, `equipments`, and `web-page` rig directories were materialized as git repositories during the 2026-05-15 discovery pass while preserving their local Gas City state.

## Confirmed Repository Landscape

The following GitHub repositories were confirmed in the `AgenticFunProject`
organization on 2026-05-15.

| Repository | Visibility | Default branch | Current role | State |
|------------|------------|----------------|--------------|-------|
| `quotes` | Public | `main` | FastAPI Quotes service with SQLite persistence, tests, product specs, Bruno collection, GitHub Actions, and Azure App Service infrastructure | Confirmed implementation |
| `booking` | Public | `master` | Booking service implementation and specification set; defines Java/Spring Boot domain, API, JWT roles, ownership checks, deployment profile expectations, and external clients for schedules, equipments, and quotes | Confirmed implementation and specification state in current checkout |
| `equipments` | Public | `master` | TypeScript/Fastify Equipments service with inventory, reservations, audit metadata, OpenAPI, tests, persisted authorization rules, Dockerfile, and Azure Container Apps manifests | Confirmed implementation |
| `web-page` | Public | `main` | Customer portal demo and local gateway/proxy; generates Equipments- and Quotes-audience demo tokens and proxies `/api/quotes`, `/api/equipment`, `/api/users`, and `/api/bookings` | Confirmed implementation |
| `users` | Private | `main` | TypeScript Users service for stable local user ids, external-identity lookup, profile/status management, local password verification, local password login, JWT signing, and Azure Container Apps scaffolding | Confirmed implementation; bearer enforcement on existing Users API routes remains deferred |

## Confirmed Azure Footprint

The Azure subscription visible from the current CLI contains one confirmed
AgenticFunProject application deployment:

| Component | Azure resource | Resource group | Notes |
|-----------|----------------|----------------|-------|
| Quotes | `app-quotes-dev-371ad1` (`Microsoft.Web/sites`) | `rg-quotes-dev-371ad1` | Running Linux container App Service at `https://app-quotes-dev-371ad1.azurewebsites.net`; system-assigned managed identity enabled |
| Quotes | `asp-quotes-dev-371ad1` | `rg-quotes-dev-371ad1` | Basic B1 Linux App Service Plan |
| Quotes | `acrquotesdev371ad1` | `rg-quotes-dev-371ad1` | Basic Azure Container Registry used by GitHub Actions deployment |
| Quotes | `appi-quotes-dev-371ad1` | `rg-quotes-dev-371ad1` | Application Insights component |

The live Quotes deployment returned `200` for `/health` and `/docs`, and
accepted a `POST /quotes` request with bounded alternatives on 2026-05-15.

No deployed Azure resources were confirmed for `booking`, `equipments`,
`web-page`, or `users` in the current subscription. `equipments` contains Azure
Container Apps manifest examples, but no matching live Container App was found
during discovery.

The live Quotes App Service was discovered before platform auth app settings
were reconciled. The current Bicep template and GitHub Actions deployment path
now supply `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE=quotes-service`, and
`AUTH_JWT_SECRET` from GitHub secret material; rerunning the deploy workflow
with `AUTH_JWT_SECRET` configured brings the App Service into that state. A
production identity architecture should eventually replace the current HS256
development contract with managed identity, OIDC/JWKS validation, or an API
gateway policy.

## 2026-05-19 Auth And Deployment Evidence Snapshot

This snapshot records the cross-repository evidence found after fetching the
AgenticFunProject remotes on 2026-05-19. It is evidence for the next Quotes
implementation plan, not proof that every component is already deployed or
connected in production.

- Users: confirmed local SQLite user records, PostgreSQL runtime support, local
  password verification, `POST /auth/token`, JWT signing with
  `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, `AUTH_JWT_SECRET`, and Azure
  Container Apps scaffolding. Bearer-token enforcement remains out of scope for
  existing Users HTTP routes.
- Equipments: confirmed HS256 bearer-token enforcement for protected routes.
  Read routes require `equipments:read`, write routes require
  `equipments:modify`, and `role=admin` is accepted for privileged equipment
  operations after normal issuer, audience, expiry, and signature validation.
  The repo also persists controller authorization rules and documents
  Key Vault-backed Azure Container Apps deployment using the shared
  `auth-jwt-secret`.
- web-page: confirmed `/api/auth/quotes-token` helper for local demo
  Quotes-audience tokens, plus `/api/quotes`, `/api/equipment`, `/api/users`,
  and `/api/bookings` proxy routes. The browser API helper currently attaches bearer tokens only to `/api/equipment`, so Quotes public request/read calls stay unauthenticated unless a later gateway workflow deliberately adds a protected Quotes operation.
- Booking: confirmed specification-only repository state is no longer accurate;
  the remote default branch now contains Spring Boot source and tests as well
  as specifications. Booking still treats Quotes through configured client
  boundaries such as `QUOTE_API_URL`. QuoteClientRestClient must not forward the caller `Authorization` header to public quote validation or lookup routes unless a future service-to-service auth contract explicitly requires it.
- Quotes Azure deployment: confirmed workflow wiring exists for
  `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE=quotes-service`, and
  `AUTH_JWT_SECRET`. The live App Service was previously confirmed, but this
  snapshot does not confirm that the latest app settings were deployed after
  the 2026-05-19 remote updates.

Gap: no live Azure Container App resources were confirmed for Users,
Equipments, Booking, or web-page from this repository snapshot, even though
Users and Equipments now contain Container Apps scaffolding.

Gap: the current Quotes service accepts `quotes:admin` and `quotes:approve`
scopes, but it does not yet document or implement `role=admin` as a scope
substitute. That compatibility decision is intentionally tracked separately.

Assumption: `platform-auth` remains the local shared issuer while the town uses
the HS256 development contract. Production should replace this with managed
identity, OIDC/JWKS validation, or an API gateway policy before exposing
privileged operations broadly.

Assumption: gateway-issued Quotes-audience tokens are a local developer and
demo helper until the platform identity source is settled.

## Quotes Repository Responsibilities

Within the current repository, the confirmed responsibilities are:

- expose the Quotes HTTP API through FastAPI
- calculate and persist quotes against local seeded or managed commercial data
- persist quote lifecycle and commercial outbox records
- carry the current product specification, scenarios, and architecture notes
- run local and CI verification through `tests/`, `scripts/verify.sh`, and GitHub Actions
- define Azure deployment assets through `infra/azure/` and workflow automation
- enforce platform bearer scopes on protected operational writes

This repository is the system's documented business boundary. It does not currently document or implement the whole town control plane.

## Service Integration Boundary

The current business-plane integration boundary is intentionally narrow.

Confirmed service-level dependencies and consumers:

- `Schedules API` is represented by a local `ScheduleProvider` abstraction backed by an in-memory stub.
- Booking is a downstream consumer of stored quote state and quote lifecycle events. The Booking repository now contains Spring Boot source and still specifies quote integration properties and `QUOTE_API_URL`.
- Equipments owns container inventory and reservation behavior. Its service already enforces HS256 bearer tokens with `scope` claims, which is the model now adopted by Quotes for protected operational writes.
- Users owns stable local user ids, external identity lookup, local password login, and local JWT issuance. Bearer-token enforcement for the existing Users routes remains deferred.
- The web-page gateway proxies `/api/quotes` to Quotes and `/api/equipment` to Equipments, and it can generate local Equipments- and Quotes-audience bearer tokens for demos.
- Quote lifecycle and managed commercial changes are persisted through an outbox-first design, with broker adoption explicitly deferred.

Implication:

- quote calculation should continue to work even if Booking, Equipments, Users, or orchestration components are unavailable, as long as the Quotes process and its local data are available
- Booking-facing flows should read persisted quote state by `id` or `quoteReference` and should consume outbox events or replay checkpoints rather than requiring synchronous callbacks from Quotes
- shared auth semantics should converge on issuer, audience, subject, and scope contracts before adding service-to-service write calls

## Control Plane Versus Business Plane

The current system is best understood as two adjacent planes.

### Business plane

- `quotes` repository
- `booking` repository
- `equipments` repository
- `web-page` repository
- `users` repository
- FastAPI application code under `app/`
- TypeScript/Fastify service code where present
- service-local persistence and tests
- product, API, and architecture specifications

### Control plane

- city and rig orchestration rooted at `/home/user/projects/gascity/examples/agenticfun`
- bead-driven work dispatch and tracking
- role behavior, workflows, orders, and session hooks supplied by the AgenticFun pack
- runtime state, logs, and hook assignments outside service source code

This boundary is important because it prevents service documentation from drifting into unsupported claims about orchestration internals while still acknowledging that the Quotes repository operates inside a larger multi-repository system.

## Known Gaps And Explicit Assumptions

### Confirmed gaps

- No Schedules repository was found in the AgenticFunProject organization during discovery.
- Booking currently provides Spring Boot source and detailed specifications, but its live deployment state was not confirmed from this repository snapshot.
- Users has local password verification, local token issuance, and stable user metadata, but bearer-token enforcement for its existing routes is explicitly deferred.
- Web-page can mint local demo tokens for Equipments and Quotes, but the browser helper currently attaches bearer tokens only to Equipments API calls.
- Quotes Azure App Service discovery predated the platform-auth deployment
  wiring; rerun the Azure deploy workflow with `AUTH_JWT_SECRET` configured to
  reconcile app settings.
- No deployed Azure resources were confirmed for Booking, Equipments, Web-page, or Users in the current subscription.

### Explicit assumptions

- `platform-auth` is the current local issuer for platform JWTs because Equipments implements it and Booking specs reference JWT-based service authorization.
- `AUTH_JWT_SECRET` is a development shared-secret contract, not a final production identity architecture.
- Booking should treat Quotes as the source of quote bookability and pricing provenance until a dedicated booking-quote contract supersedes the current endpoints.

## Expected Evolution

Near-term architecture evolution already implied by the Quotes specifications:

1. Replace the in-memory schedules stub with a real schedules integration behind the existing provider boundary.
2. Keep Booking as a downstream consumer of stored quote state, with tighter documented contracts as Booking integration becomes concrete.
3. Continue with the outbox-first eventing model until at least two meaningful downstream consumers justify broker adoption.
4. Decide whether the web-page gateway should attach Quotes-audience tokens for any protected Quotes operations exposed in local demos; keep public quote create/read traffic unauthenticated by default.
5. Add or implement Booking clients for `GET /quotes/{id}`, `GET /quotes/{id}/bookability`, and outbox replay after Booking source code exists.
6. Replace shared HS256 development secrets with managed identity, OIDC/JWKS validation, or an API gateway policy before production exposure.

## Documentation Contract

When this document is updated, keep these invariants true:

- `specification/quotes.md` remains the service contract for business behavior.
- this document remains the broader repository and boundary map for the current system state.
- every non-confirmed statement is labeled as an assumption or gap rather than presented as settled architecture.
