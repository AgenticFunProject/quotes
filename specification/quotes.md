# Component: Quotes Service

## Purpose
Calculates and returns freight prices for a given schedule, equipment selection, and cargo weight.
Provides a quoted price that can be referenced when placing a booking.

## Responsibilities
- Accept a rate request (schedule + equipment + weight)
- Apply freight rates and surcharges to produce a total price
- Store quotes with a validity period so they can be referenced by Booking
- Return itemised price breakdown

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /quotes | Request a new quote |
| GET | /quotes/{id} | Retrieve a quote by internal ID or public quote reference |

### POST /quotes - Request Body
```json
{
  "scheduleId": "string",
  "equipment": [
    { "type": "20FT", "quantity": 2 },
    { "type": "40FT", "quantity": 1 }
  ],
  "cargoWeightKg": 18000
}
```

### POST /quotes - Response
```json
{
  "quoteId": "QTE-2026-00108",
  "validUntil": "2026-04-07T23:59:59Z",
  "currency": "USD",
  "lineItems": [
    { "description": "Ocean Freight - 20FT x 2", "amount": 1800.00 },
    { "description": "Ocean Freight - 40FT x 1", "amount": 1400.00 },
    { "description": "Bunker Adjustment Factor (BAF)", "amount": 320.00 },
    { "description": "Port Surcharge - Destination", "amount": 150.00 }
  ],
  "totalAmount": 3670.00
}
```

## Pricing Logic

### Base Freight Rate
- Rates are defined per **trade lane** (origin region -> destination region) and **equipment type**
- Rate table: `(originPort, destinationPort, equipmentType) -> baseRateUSD`

### Surcharges Applied Automatically
| Surcharge | Basis |
|-----------|-------|
| Bunker Adjustment Factor (BAF) | Per container |
| Port Congestion Surcharge | Per container, if applicable to port |
| Heavy Cargo Surcharge | Per container when weight exceeds threshold (e.g. > 20 000 kg per TEU) |
| Peak Season Surcharge (PSS) | Per container, date-range based |

### Quote Validity
- Quotes are valid for **7 days** from creation by default
- Expired quotes cannot be used to create bookings

## Data Model (Quote)
| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Internal primary key |
| quoteReference | string | Human-readable (QTE-YYYY-NNNNN) |
| scheduleId | UUID | |
| equipment | JSON array | type + quantity |
| cargoWeightKg | number | |
| currency | string | ISO 4217, default USD |
| lineItems | JSON array | description + amount |
| totalAmount | decimal | |
| validUntil | timestamp | |
| createdAt | timestamp | |

## Data Model (Rate Table)
| Field | Type | Notes |
|-------|------|-------|
| id | UUID | |
| originPort | string | UN/LOCODE |
| destinationPort | string | UN/LOCODE |
| equipmentType | enum | 20FT, 40FT, 40FT_HC |
| baseRateUSD | decimal | |
| validFrom | date | Rate effective date |
| validTo | date | Rate expiry date |

## Dependencies
| Service | Why |
|---------|-----|
| Schedules API | Validate scheduleId and resolve origin/destination ports |

## Current Integration Boundaries
- `Schedules API` is the only explicitly documented external dependency in this specification.
- In the current implementation, `Schedules API` is represented by a local static schedule stub keyed by `scheduleId`.
- Equipment data is currently modeled inside this service through request payloads, supported equipment types, TEU conversion rules, and seeded rate data.
- Booking is currently a downstream consumer of quotes rather than an active runtime dependency. The service stores quotes with validity so Booking can reference them later.
- The frontend is expected to consume the HTTP API exposed by this service. There is no frontend-specific integration layer in this repository yet.

## Current Implementation Notes
- `POST /quotes` returns the commercial quote payload only: `quoteId`, `validUntil`, `currency`, `lineItems`, and `totalAmount`.
- `GET /quotes/{id}` accepts either the internal quote UUID or the human-readable `quoteReference` returned as `quoteId` during quote creation and returns the stored record, including both identifiers.
- Quote references are generated sequentially within the current UTC year using the `QTE-YYYY-NNNNN` format.
- A schedule lookup and a quoteable lane are not the same thing in the current implementation: a known `scheduleId` can still return `400` when no effective base rate exists for the route, equipment, and departure date.
- These notes describe the present behavior of the generated code and should be folded into the business specification when they are confirmed as intended behavior.

## Out of Scope (v1)
### Customer-specific contract rates / negotiated tariffs
- Quotes are generated from the standard rate table and surcharge rules only.
- The service does not apply customer identity, account ownership, contract entitlements, negotiated discounts, or long-term tariff agreements when calculating a quote.
- Two users requesting the same schedule, equipment, and cargo weight should receive the same commercial result in v1.

### Multi-currency conversion
- Quote amounts are produced in a single currency only.
- The service does not convert rates between currencies, fetch exchange rates, round according to market-specific currency rules, or expose alternative currencies in the response.
- Any future support for additional billing or display currencies is outside the v1 pricing contract.

### Spot rate market integration
- The service does not query external freight marketplaces, broker feeds, carrier APIs, or dynamic market-pricing sources.
- Quote generation is based only on the internally available schedule context, rate table data, and surcharge rules defined for this service.
- Real-time market volatility, bidding, and externally sourced price recommendations are excluded from v1 behavior.

### Automatic rate management / revenue optimization
- The service does not change rates or surcharge rules autonomously.
- It does not optimize price based on demand, lane utilization, capacity pressure, customer segment, margin targets, or competitive market conditions.
- Any future pricing strategy engine, revenue management logic, or machine-assisted repricing workflow is explicitly outside the v1 scope.

## Future Implementation Guidance

This section defines how currently excluded capabilities should behave when they are introduced in a later version. These rules describe business logic and evaluation order rather than a required technical design.

### Customer-specific contract rates / negotiated tariffs

#### Business goal
- Allow a quote request to produce customer-specific commercial terms when the requesting party has an active contract or negotiated tariff.

#### Required inputs
- A customer identifier or account identifier that can be resolved to a commercial profile.
- A contract context containing at least:
  - validity window
  - covered trade lanes or ports
  - covered equipment types
  - contract rate or discount rule
  - contract priority when multiple agreements exist

#### Decision logic
1. Validate the schedule and requested equipment as in v1.
2. Resolve whether the requester has one or more active contracts applicable to the shipment date.
3. Filter contracts to those matching the route, equipment type, and commercial eligibility rules.
4. If multiple contracts are applicable, select one deterministically using a documented precedence order.
5. Use the selected contract pricing as the base freight input.
6. Apply surcharge rules on top unless the contract explicitly overrides or waives a surcharge.
7. Record in the stored quote which commercial basis was used, so Booking can later validate that the quote was created under the correct commercial terms.

#### Precedence rules
- A future version should define a deterministic precedence such as:
  - exact customer contract overrides account-level contract
  - account-level contract overrides public tariff
  - more specific lane match overrides broader regional match
  - explicit negotiated fixed price overrides percentage discount
  - newest active contract version overrides older active contract version when both are otherwise equal

#### Expected outcomes
- Two different customers may receive different quotes for the same schedule and equipment request.
- The same customer should receive the same quote result for the same request while the underlying pricing inputs remain unchanged.

### Multi-currency conversion

#### Business goal
- Allow a quote to be returned in a requested commercial currency while preserving a deterministic pricing basis.

#### Required inputs
- A requested response currency.
- An exchange-rate source with an effective timestamp or trading date.
- A rounding policy per currency.

#### Decision logic
1. Calculate the quote using a single pricing source currency.
2. Determine whether the client requested the pricing currency or a display currency.
3. Resolve the exchange rate effective for the quote creation time according to a documented rule.
4. Convert each monetary value according to a consistent conversion policy.
5. Apply currency-specific rounding rules in a deterministic place in the calculation flow.
6. Return both the response currency and enough metadata for downstream systems to understand how the amount was derived.

#### Deterministic rules to define
- Whether conversion happens:
  - per line item and then summed
  - or on the total after all source-currency line items are finalized
- Whether the exchange rate is selected by:
  - quote creation timestamp
  - shipment date
  - business day closing rate
- How currencies with different minor units are rounded.

#### Expected outcomes
- Re-running the same request against the same exchange-rate snapshot should reproduce the same monetary result.
- Booking should be able to validate the booked amount against the quote without ambiguity about the conversion basis.

### Spot rate market integration

#### Business goal
- Allow the quotes service to incorporate real-time or near-real-time market prices when the business chooses to price a shipment dynamically instead of using only static tariffs.

#### Required inputs
- One or more approved market-pricing sources.
- A normalization rule that converts source market data into the quote domain.
- A fallback policy when no usable market rate is available.

#### Decision logic
1. Resolve whether the requested lane and shipment timing are eligible for market-based pricing.
2. Query the configured market source or sources.
3. Normalize external price offers into a comparable internal structure.
4. Discard expired, incomplete, or commercially invalid market offers.
5. Select a market price using a deterministic ranking method.
6. If no acceptable market price exists, fall back to the configured tariff or contract pricing path.
7. Apply surcharges and quote-validity rules according to the pricing mode.

#### Selection rules to define
- Future behavior should explicitly define:
  - whether best price, preferred carrier, or preferred service level wins
  - how source freshness is measured
  - whether a market quote can be blended with tariff-based surcharges
  - how long a market-based quote remains valid before repricing is required

#### Expected outcomes
- The service should still produce a quote when market data is unavailable, using a documented fallback path.
- The quote should capture whether it was produced from tariff pricing, contract pricing, market pricing, or a hybrid model approved by the business rules.

### Automatic rate management / revenue optimization

#### Business goal
- Allow the commercial organization to adjust pricing dynamically based on revenue goals and operational conditions while keeping the decision path auditable.

#### Required inputs
- Pricing strategy rules or optimization policies.
- Operational signals such as capacity pressure, lane utilization, seasonality, or booking pace.
- Commercial guardrails such as minimum margin, maximum discount, and permitted override scope.

#### Decision logic
1. Start from the selected commercial base price source.
2. Evaluate whether the shipment is eligible for automated optimization.
3. Apply strategy rules in a documented order, for example lane pressure adjustments before promotional adjustments.
4. Enforce guardrails so the final price cannot violate policy.
5. Persist the strategy decisions used to produce the final quote.
6. Return the final customer-facing line items and totals without exposing internal strategy details unless explicitly required.

#### Governance rules
- Any future implementation should define:
  - which inputs are advisory versus mandatory
  - whether optimizations can change base rate, surcharge, or both
  - when human approval is required
  - how A/B testing or experiment-driven pricing is isolated from normal quoting behavior
  - how Booking validates that the optimized quote is still bookable at the stored amount

#### Expected outcomes
- The optimization path must be reproducible from stored inputs and rule versions.
- Two identical requests evaluated under the same strategy snapshot should produce the same result.
- The service should be able to explain which pricing mode produced the quote even if the customer-facing response remains simplified.
