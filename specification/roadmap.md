# Quotes Service Roadmap

## Goal

Turn the current quote calculator into a booking-ready pricing service with a clear path from seeded demo behavior to durable commercial integrations.

## Current State

The service already supports a useful v1 slice:

- synchronous `POST /quotes` pricing and `GET /quotes/{id}` retrieval
- persisted quotes with a 7-day validity period
- seeded rate tables and surcharge rules in SQLite
- schedule validation via a local in-process stub

The main gaps are commercial context, integration boundaries, and operational hooks for downstream consumers such as Booking.

## Product Principles

- Keep quote creation deterministic and auditable.
- Add commercial complexity in phases instead of mixing contract, currency, market, and optimization work into one release.
- Preserve a simple synchronous API for quote creation even if downstream notifications become asynchronous later.
- Make every future pricing mode explainable from stored inputs and rule versions.

## Phase 1: Productionize The Current Quote Contract

### User-facing outcomes

- Stabilize the current API as a documented baseline for frontend and Booking integration.
- Make quote lookup semantics clearer for internal and external consumers.
- Capture enough metadata to explain how a quote was produced.

### Recommended API changes

- Keep `POST /quotes` synchronous and backward compatible.
- Add `GET /quotes/reference/{quoteReference}` so downstream systems can retrieve a quote by the identifier returned from quote creation.
- Add a response field such as `pricingBasis` with values like `PUBLIC_TARIFF`.
- Add `scheduleSnapshot` or equivalent stored route metadata to avoid depending on a mutable schedule service for later validation.

### Recommended data model changes

- `quotes`
- Add `originPort`
- Add `destinationPort`
- Add `departureDate`
- Add `pricingBasis`
- Add `pricingInputVersion` or `rateSnapshotVersion`
- Add `status` with an initial lifecycle such as `ACTIVE`, `EXPIRED`, `CONSUMED`
- Normalize `lineItems` and `equipment` into dedicated tables if reporting or downstream reconciliation becomes important.

### Delivery notes

- Move the schedule stub behind an adapter interface so the service can later swap in the real Schedules API without rewriting quote creation.
- Keep SQLite for local development, but ensure schema migrations are in place before adding more commercial state.

## Phase 2: Booking-Ready Commercial Rules

### User-facing outcomes

- Support customer-specific contract pricing.
- Let Booking validate whether a quote is still bookable.
- Preserve the exact commercial basis used to create each quote.

### Recommended API changes

- Extend `POST /quotes` with a customer or account identifier.
- Add `POST /quotes/{id}/validate` or `GET /quotes/{id}/eligibility` for Booking-time validation.
- Return quote lifecycle metadata such as `status`, `expired`, and `bookable`.

### Recommended data model changes

- `contracts`
- `contract_rate_rules`
- `quote_pricing_decisions` for the selected tariff or contract path
- `quote_events` or an outbox table for downstream integration

### Delivery notes

- Contract evaluation should remain deterministic: the service must store which contract or tariff row won and why.
- Booking should validate against stored quote state, not recompute prices from scratch.

## Phase 3: Multi-Currency And External Market Inputs

### User-facing outcomes

- Return quotes in a requested currency.
- Blend public tariffs, contract rates, and approved market rates through a documented selection order.

### Recommended API changes

- Accept `requestedCurrency` on quote creation.
- Add response metadata for exchange-rate source and effective timestamp.
- Add optional commercial metadata describing whether pricing came from tariff, contract, or market mode.

### Recommended data model changes

- `exchange_rates`
- `market_rate_snapshots`
- additional quote fields for `sourceCurrency`, `exchangeRateRef`, and `pricingMode`

### Delivery notes

- Introduce market pricing only after the contract path is stable, otherwise fallback logic becomes difficult to reason about.
- Persist normalized external offers before using them in pricing decisions.

## Phase 4: Revenue Optimization And Event-Driven Consumers

### User-facing outcomes

- Support controlled dynamic pricing adjustments.
- Feed downstream consumers such as analytics, audit, and revenue tooling without coupling quote creation to those systems.

### Recommended API changes

- Keep the quote API synchronous.
- Expose customer-safe quote results while storing richer internal decision metadata separately.

### Recommended data model changes

- `pricing_strategy_versions`
- `quote_adjustments`
- expanded event payloads for quote lifecycle changes

### Delivery notes

- Optimization must layer on top of stored base pricing decisions and guardrails.
- This is the point where a real message broker becomes materially useful because multiple consumers will exist with different replay and latency needs.

## Architecture Work Items By Order

1. Introduce migrations and explicit repository/service boundaries around quote creation.
2. Replace the in-process schedule stub with a schedule provider interface.
3. Persist quote decision metadata and lifecycle state.
4. Add an outbox-based event model for quote lifecycle notifications.
5. Add contract pricing support.
6. Add booking validation semantics.
7. Add currency conversion.
8. Add external market pricing.
9. Add optimization rules.
10. Introduce a broker only after outbox events have at least two meaningful downstream consumers.

## Suggested Near-Term Definition Of Done

The next substantial milestone should deliver:

- quote retrieval by public `quoteReference`
- persisted quote lifecycle state
- schedule provider abstraction
- outbox-backed quote lifecycle events
- contract-ready decision metadata on stored quotes

That milestone keeps the current service simple while creating the foundation needed for Booking and future pricing modes.
