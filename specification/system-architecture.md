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
| `booking` | Public | `master` | Booking service specification set; defines Java/Spring Boot domain, API, JWT roles, ownership checks, and future external clients for schedules, equipments, and quotes | Specification only in current checkout |
| `equipments` | Public | `master` | TypeScript/Fastify Equipments service with inventory, reservations, audit metadata, OpenAPI, tests, Dockerfile, and Azure Container Apps manifests | Confirmed implementation |
| `web-page` | Public | `main` | Customer portal demo and local gateway/proxy; generates Equipments-compatible dev tokens and proxies `/api/quotes` plus `/api/equipment` | Confirmed implementation |
| `users` | Private | `main` | TypeScript Users service for stable local user ids, external-identity lookup, profile/status management, and local password verification | Confirmed implementation; bearer enforcement deferred by its README |

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

The current Quotes App Service settings include `DATABASE_URL`,
`APPLICATIONINSIGHTS_CONNECTION_STRING`, `WEBSITES_PORT`, container registry
settings, and no platform auth settings yet. A production deployment should set
`AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, and `AUTH_JWT_SECRET` or replace the
current HS256 development contract with managed identity or an OIDC verifier.

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
- Booking is a downstream consumer of stored quote state and quote lifecycle events. The Booking repository currently specifies quote integration properties and `QUOTE_API_URL`, but has no implementation code in this checkout.
- Equipments owns container inventory and reservation behavior. Its service already enforces HS256 bearer tokens with `scope` claims, which is the model now adopted by Quotes for protected operational writes.
- Users owns stable local user ids and external identity lookup. Its README explicitly says bearer-token enforcement is still deferred.
- The web-page gateway proxies `/api/quotes` to Quotes and `/api/equipment` to Equipments, and it can generate local Equipments-compatible bearer tokens for demos.
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
- Booking currently provides detailed Spring Boot specifications but no application source in the current checkout.
- Users has local password verification and stable user metadata, but bearer-token enforcement is explicitly deferred.
- Web-page can mint local demo tokens for Equipments but does not yet mint Quotes-audience tokens.
- Quotes Azure App Service is deployed, but its current app settings do not yet include platform auth secret/issuer/audience settings.
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
4. Add Quotes-audience token support to the web-page gateway when protected Quotes operations are exposed through local demos.
5. Add or implement Booking clients for `GET /quotes/{id}`, `GET /quotes/{id}/bookability`, and outbox replay after Booking source code exists.
6. Replace shared HS256 development secrets with managed identity, OIDC/JWKS validation, or an API gateway policy before production exposure.

## Documentation Contract

When this document is updated, keep these invariants true:

- `specification/quotes.md` remains the service contract for business behavior.
- this document remains the broader repository and boundary map for the current system state.
- every non-confirmed statement is labeled as an assumption or gap rather than presented as settled architecture.
