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
