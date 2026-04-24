## Quotes Service Roadmap

This document turns `specification/quotes.md` into a concrete delivery roadmap for the next phases of the Quotes service.

### Current State

- Quote generation is synchronous and request-driven.
- Schedule validation is backed by an in-process stub rather than a live dependency.
- Pricing uses seeded base rates and surcharge rules stored locally.
- Quotes are persisted and can be retrieved later, but downstream lifecycle behavior is still minimal.

### Product Goals

1. Make quotes commercially trustworthy.
2. Make pricing inputs auditable and reproducible.
3. Support differentiated pricing by customer and market context.
4. Decouple downstream reactions from the synchronous quote API.

### Product Principles

- Keep quote creation synchronous until asynchronous workflows provide clear operational value.
- Add one source of commercial complexity at a time: lifecycle first, then governed pricing data, then customer contracts, then currencies, then market and optimization logic.
- Persist enough pricing context that Booking and support workflows can validate a quote without recomputing it from mutable upstream data.
- Prefer explicit pricing modes and rule versions over implicit behavior.

## Dependency Order

The phases are not independent. Later phases assume earlier infrastructure and domain concepts are already stable.

| Capability | Depends on | Why |
|------------|------------|-----|
| Quote lifecycle status | Real schedule integration | Quote validity and downstream validation need durable shipment context |
| Managed commercial data | Quote lifecycle status | Rate versions and surcharge governance should attach to a stable quote model |
| Contract pricing | Managed commercial data | Contract evaluation must resolve against governed tariff inputs |
| Multi-currency | Contract pricing or tariff provenance | FX conversion is only trustworthy when the source commercial basis is explicit |
| Event-driven integration | Lifecycle, provenance, and governed inputs | Stable events require stable domain concepts and payloads |
| Market pricing and optimization | Eventing plus provenance | Dynamic pricing needs both durable inputs and downstream observability |

## Delivery Phases

### Phase 1: Production-Ready Quote Lifecycle

Goal: make the current quote flow dependable before adding advanced pricing modes.

Scope:
- Replace the schedule stub with a real schedules integration.
- Add explicit quote status semantics: active, expired, revoked.
- Support retrieval by both internal ID and `quoteReference`.
- Add a booking validation endpoint so downstream consumers can verify that a quote is still usable.
- Add idempotency support on quote creation to prevent duplicate quotes from retries.

Likely API changes:
- `POST /quotes` accepts an optional idempotency key header.
- `GET /quotes/{id}` accepts either UUID or quote reference.
- `GET /quotes/{id}/bookability` returns lifecycle and validation state.

Likely data model changes:
- `quotes.status`
- `quotes.expired_at` or computed lifecycle metadata
- `quotes.pricing_basis`
- `quotes.idempotency_key`
- `quotes.schedule_snapshot` or schedule version metadata

Success criteria:
- Booking can validate a quote without recomputing price.
- The service can explain whether a quote is expired or otherwise unusable.

### Phase 2: Managed Commercial Data

Goal: move from seeded demo pricing data to operationally managed rates and surcharges.

Scope:
- Add rate table administration and import workflows.
- Add surcharge rule versioning and effective-date management.
- Add audit fields for who changed commercial data and when.
- Add preview tooling for commercial teams to test upcoming rates before activation.

Likely API changes:
- Admin endpoints or separate internal APIs for rate and surcharge management.
- Validation endpoints for rate coverage by trade lane and equipment type.

Likely data model changes:
- `rate_tables.version`
- `rate_tables.created_by`
- `surcharge_rules.version`
- `surcharge_rules.is_active`
- `commercial_change_events` or equivalent audit table

Success criteria:
- Commercial data can change without code deployment.
- Quote provenance can identify the exact rate and surcharge versions used.

### Phase 3: Contract and Customer Pricing

Goal: support negotiated tariffs and customer-specific commercial outcomes.

Scope:
- Accept customer or account context on quote requests.
- Resolve applicable contracts using deterministic precedence rules.
- Allow contracts to override base rates and optionally waive surcharges.
- Persist the commercial basis used for each quote.

Likely API changes:
- `POST /quotes` accepts `customerId` or `accountId`.
- Quote responses expose pricing mode metadata, either directly or through an internal details endpoint.

Likely data model changes:
- `contracts`
- `contract_lane_rules`
- `contract_equipment_rules`
- `quotes.contract_id`
- `quotes.pricing_mode` with values such as `PUBLIC_TARIFF` and `CONTRACT`

Success criteria:
- Two customers can receive different prices for the same shipment inputs.
- Booking can validate the quote against the stored contract basis.

### Phase 4: Multi-Currency and Monetary Provenance

Goal: support commercial currencies without losing reproducibility.

Scope:
- Allow a requested response currency.
- Source FX rates from a governed provider.
- Persist the FX snapshot and rounding policy used at quote time.
- Decide and document whether conversion happens per line item or on the final total.

Likely API changes:
- `POST /quotes` accepts `currency`.
- Quote responses include source currency, response currency, and FX metadata.

Likely data model changes:
- `quotes.source_currency`
- `quotes.response_currency`
- `quotes.fx_rate`
- `quotes.fx_rate_timestamp`
- `quotes.rounding_policy`

Success criteria:
- Re-running the same quote against the same FX snapshot produces the same result.
- Booking and finance can reconcile the quote amount unambiguously.

### Phase 5: Event-Driven Integration

Goal: decouple quote creation from downstream reactions and create a durable commercial event stream.

Scope:
- Publish quote lifecycle and commercial data change events.
- Add consumers for booking validation caches, notifications, analytics, and audit sinks.
- Introduce asynchronous impact workflows for schedule and contract changes.

Candidate events:
- `quote.created`
- `quote.expired`
- `quote.revoked`
- `rate.updated`
- `surcharge.updated`
- `contract.updated`
- `schedule.changed`
- `fx.rate.published`

Likely API changes:
- No customer-facing API changes required at first.
- Internal admin and replay tooling will be needed.

Likely data model changes:
- `outbox_events`
- consumer checkpoint storage or stream processor state
- impact-analysis tables for affected quotes

Success criteria:
- Downstream systems react to quote and pricing changes without synchronous coupling.
- Event replay can rebuild dependent read models or caches.

### Phase 6: Market Pricing and Revenue Optimization

Goal: introduce dynamic pricing safely after governance and provenance are in place.

Scope:
- Integrate approved spot-market sources.
- Add fallback from market pricing to tariff or contract pricing.
- Introduce strategy rules based on capacity pressure, utilization, or seasonality.
- Persist the optimization rule path used for each quote.

Likely API changes:
- Optional pricing mode hints on quote requests.
- Internal explainability endpoints for support and audit workflows.

Likely data model changes:
- `market_rate_snapshots`
- `pricing_strategy_versions`
- `quotes.market_source`
- `quotes.optimization_trace`

Success criteria:
- Dynamic pricing remains reproducible under a stored strategy snapshot.
- The service can explain whether a quote came from tariff, contract, market, or optimized pricing.

## Recommended Build Order

1. Phase 1: Production-ready quote lifecycle
2. Phase 2: Managed commercial data
3. Phase 3: Contract and customer pricing
4. Phase 4: Multi-currency and monetary provenance
5. Phase 5: Event-driven integration
6. Phase 6: Market pricing and revenue optimization

This order keeps early work focused on correctness and governance before introducing operational complexity.

## Near-Term Milestone

The next substantial milestone should make the service booking-ready without adding market or optimization complexity.

### Milestone Name

Milestone A: Booking-ready quote foundation

### Scope

- Replace the schedule stub with a provider abstraction and initial real integration path.
- Store schedule snapshot data directly on the quote so downstream validation does not depend on mutable schedule state.
- Add quote lifecycle status with an initial state model such as `ACTIVE`, `EXPIRED`, and `CONSUMED`.
- Support lookup by `quoteReference` in addition to internal UUID.
- Add booking validation semantics through a dedicated endpoint.
- Persist pricing provenance fields that identify the pricing mode and source rule version used.

### Definition Of Done

- A caller can create a quote and later retrieve it using the same public quote reference returned at creation time.
- Booking can ask whether the quote is still usable without recalculating price.
- The stored quote record contains enough route and pricing metadata to explain how the amount was produced.
- Schedule integration details are behind an adapter boundary rather than embedded in endpoint code.

### Implementation Backlog

The following slices are small enough to implement independently while still moving Milestone A forward.

1. Add a schedule provider abstraction around the current stub.
2. Add schema migration support for quote lifecycle and provenance fields.
3. Persist schedule snapshot data on quote creation.
4. Add quote lifecycle status and expiry evaluation rules.
5. Support quote retrieval by public `quoteReference`.
6. Add a booking validation endpoint and response contract.
7. Add idempotency key handling for `POST /quotes`.
8. Update API tests to cover lifecycle, lookup, and validation behavior.
9. Update `README.md` and `specification/quotes.md` so runtime behavior and specification no longer drift.

### Suggested Bead Breakdown

1. Introduce `ScheduleProvider` interface and move the stub behind it.
2. Add quote schema fields: status, pricing basis, idempotency key, and schedule snapshot.
3. Implement lookup by `quoteReference`.
4. Implement `GET /quotes/{id}/bookability`.
5. Add persistence and tests for pricing provenance metadata.
6. Reconcile spec and README documentation with the implemented API.

### Explicitly Deferred

- customer-specific contracts
- multi-currency responses
- market feeds
- optimization strategies
- broker-backed event delivery

## Delivery Risks

### Domain Risks

- Quote validity may become ambiguous if future schedule changes are allowed to retroactively affect stored quotes.
- Contract pricing can become nondeterministic if precedence rules are not formalized before implementation.
- FX support can introduce reconciliation errors if rounding and conversion timing are left implicit.

### Technical Risks

- Adding commercial features without schema migrations will make data evolution brittle.
- Continuing to rely on JSON blobs for all pricing structures may limit validation, reporting, and reconciliation.
- Introducing a broker before event payloads stabilize will create churn in topics and consumers.

### Mitigations

- Persist schedule and pricing snapshots at quote creation time.
- Version pricing inputs and decision outputs early.
- Introduce an outbox before introducing Kafka.
- Normalize quote decision data incrementally when reporting needs become concrete.

## Open Questions

These should be answered before or during Milestone A, because they affect both API shape and stored quote semantics.

1. Should `GET /quotes/{id}` accept both UUID and `quoteReference`, or should public-reference lookup use a dedicated path such as `GET /quotes/reference/{quoteReference}`?
2. What lifecycle transition marks a quote as no longer reusable by Booking: expiry only, or also partial consumption, schedule change, or commercial revocation?
3. Should schedule details be stored as a full snapshot on the quote, or as a minimal route-and-date snapshot plus an upstream schedule version?
4. At what point should `lineItems` and equipment selections be normalized into dedicated tables rather than remaining JSON payloads?

## Milestone A API Sketch

This section describes a concrete, low-risk API shape for the next implementation phase.

### Create Quote

Request:

```http
POST /quotes
Idempotency-Key: 7f6f0e9d-a2b8-4c6e-bf34-98f2a4a8c2ce
Content-Type: application/json

{
  "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
  "equipment": [
    { "type": "20FT", "quantity": 1 }
  ],
  "cargoWeightKg": 18000
}
```

Response:

```json
{
  "quoteId": "QTE-2026-00108",
  "validUntil": "2026-04-07T23:59:59Z",
  "currency": "USD",
  "pricingBasis": "PUBLIC_TARIFF",
  "status": "ACTIVE",
  "lineItems": [
    { "description": "Ocean Freight - 20FT x 1", "amount": 950.0 },
    { "description": "Bunker Adjustment Factor (BAF)", "amount": 80.0 },
    { "description": "Peak Season Surcharge", "amount": 120.0 }
  ],
  "totalAmount": 1150.0
}
```

### Retrieve Quote By Public Reference

Recommended shape:

```http
GET /quotes/reference/QTE-2026-00108
```

Recommended response:

```json
{
  "id": "7d3fc6cf-2c58-4b3b-b5c5-0aa05dfaf7c2",
  "quoteReference": "QTE-2026-00108",
  "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
  "status": "ACTIVE",
  "pricingBasis": "PUBLIC_TARIFF",
  "scheduleSnapshot": {
    "originPort": "NLRTM",
    "destinationPort": "USNYC",
    "departureDate": "2026-08-18"
  },
  "equipment": [
    { "type": "20FT", "quantity": 1 }
  ],
  "cargoWeightKg": 18000.0,
  "currency": "USD",
  "lineItems": [
    { "description": "Ocean Freight - 20FT x 1", "amount": 950.0 },
    { "description": "Bunker Adjustment Factor (BAF)", "amount": 80.0 },
    { "description": "Peak Season Surcharge", "amount": 120.0 }
  ],
  "totalAmount": 1150.0,
  "validUntil": "2026-04-07T23:59:59Z",
  "createdAt": "2026-03-31T10:15:00Z"
}
```

### Quote Bookability Check

Request:

```http
GET /quotes/QTE-2026-00108/bookability
```

Response:

```json
{
  "quoteReference": "QTE-2026-00108",
  "status": "ACTIVE",
  "bookable": true,
  "reason": null,
  "validUntil": "2026-04-07T23:59:59Z",
  "pricingBasis": "PUBLIC_TARIFF"
}
```

Expired response example:

```json
{
  "quoteReference": "QTE-2026-00108",
  "status": "EXPIRED",
  "bookable": false,
  "reason": "QUOTE_EXPIRED",
  "validUntil": "2026-04-07T23:59:59Z",
  "pricingBasis": "PUBLIC_TARIFF"
}
```

## Milestone A Data Model Appendix

The fields below are a practical extension of the current quote model, not a full future-state schema.

### `quotes`

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID | Internal identifier |
| `quote_reference` | string | Public quote identifier |
| `schedule_id` | string | Upstream schedule identifier |
| `origin_port` | string | Persisted route snapshot |
| `destination_port` | string | Persisted route snapshot |
| `departure_date` | date | Persisted shipment timing snapshot |
| `equipment` | JSON | Request equipment selection |
| `cargo_weight_kg` | decimal | Request cargo weight |
| `currency` | string | Response currency for Milestone A, still USD |
| `line_items` | JSON | Customer-facing price breakdown |
| `total_amount` | decimal | Final commercial total |
| `status` | enum | `ACTIVE`, `EXPIRED`, `CONSUMED`, `REVOKED` |
| `pricing_basis` | enum | `PUBLIC_TARIFF` in Milestone A |
| `pricing_input_version` | string or null | Version marker for rates and surcharge inputs |
| `idempotency_key` | string or null | Request replay protection |
| `valid_until` | timestamp | Quote validity boundary |
| `created_at` | timestamp | Creation timestamp |

### `quote_pricing_decisions`

This can remain embedded initially, but a dedicated table becomes useful once contracts and optimization logic arrive.

| Field | Type | Purpose |
|-------|------|---------|
| `quote_id` | UUID | Parent quote |
| `decision_type` | string | `BASE_RATE`, `SURCHARGE_RULE`, `LIFECYCLE_RULE` |
| `source_type` | string | `RATE_TABLE`, `SURCHARGE_RULE`, `SYSTEM_RULE` |
| `source_id` | string | Identifier for the winning rule |
| `source_version` | string or null | Rule version used |
| `notes` | string or null | Human-readable audit detail |

### `outbox_events`

This table is not required to publish to Kafka immediately, but it is the preferred bridge when event publication is introduced.

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID | Event identifier |
| `aggregate_type` | string | `QUOTE` |
| `aggregate_id` | UUID | Related quote |
| `event_type` | string | `quote.created`, `quote.expired`, etc. |
| `payload` | JSON | Versioned event payload |
| `published_at` | timestamp or null | Relay status |
| `created_at` | timestamp | Event creation timestamp |

### Recommended Normalization Boundary

Keep `equipment` and `line_items` as JSON for Milestone A unless reporting requirements become immediate. Normalize them only when one of these becomes true:

- Booking needs relational joins against individual line items.
- Finance needs structured reconciliation by surcharge type.
- Analytics starts filtering heavily on equipment and charge components.

## ADR: Event Backbone for Quotes

### Title

ADR-001: Introduce event publication after pricing governance, not before.

### Status

Proposed

### Context

The current Quotes service is a compact synchronous API. Quote creation, pricing, storage, and retrieval all happen inside a single request path with local persistence. There is no current need for asynchronous internal orchestration to calculate a quote.

At the same time, the roadmap introduces several future requirements that naturally create cross-service reactions:

- booking validation against stored quote state
- schedule change impact detection
- contract and tariff change propagation
- FX snapshot distribution
- analytics and audit consumers
- future optimization signals based on operational events

The question is whether to add Kafka now as part of the core quote implementation, or later once those integration pressures are real.

### Decision

Do not introduce Kafka into the synchronous quote-calculation path in the near term.

Introduce an event backbone only after Phases 1 through 4 establish stable lifecycle semantics, governed pricing inputs, and quote provenance. When introduced, use the event backbone for publishing domain events and powering downstream consumers, not for the initial in-request pricing calculation.

### Rationale

1. The current service does not have enough asynchronous behavior to justify Kafka operationally.
2. Early complexity should go toward pricing correctness, contract logic, and auditability.
3. Event publication becomes materially useful once downstream systems need to react to quote, rate, contract, and schedule changes.
4. Stable domain events require stable domain concepts; adding Kafka before lifecycle and pricing semantics settle will create churn in topic design and consumers.

### Where Eventing Should Be Used

Use eventing for:
- quote lifecycle publication
- commercial data change propagation
- schedule change impact processing
- cache invalidation and read-model refreshes
- analytics, audit, and notification consumers
- operational signals for later pricing optimization

Do not use eventing initially for:
- base quote calculation inside `POST /quotes`
- simple in-process module communication
- local rule evaluation between pricing components

### Implementation Guidance

Start with an outbox pattern in the Quotes service:

1. Persist quote and domain state changes in the primary database.
2. Write outbound events to an `outbox_events` table in the same transaction.
3. Relay those events to Kafka or another broker asynchronously.
4. Make events versioned and explicitly named.

This keeps the request path reliable while allowing the service to add durable event publication later.

### Consequences

Positive:
- avoids premature broker complexity
- keeps the quote API fast and understandable
- enables future decoupling without redesigning the request path
- supports replayable downstream integrations once the domain matures

Tradeoffs:
- downstream consumers remain synchronously coupled in earlier phases
- some later refactoring will be required when event publication is introduced

### Revisit Trigger

Revisit this decision when any of the following become true:

- Booking needs near-real-time quote lifecycle events.
- Rate, contract, or schedule updates need fan-out to multiple services.
- Analytics or notification workloads start reading transactional tables directly.
- Revenue optimization requires operational signals from outside the Quotes service.
