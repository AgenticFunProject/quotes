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
| GET | /quotes/{id} | Retrieve a quote by ID |

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
- The current implementation also allows quote retrieval by `quoteReference` on `GET /quotes/{id}` in addition to internal UUID lookup.
- The current implementation returns both the internal `id` and the human-readable `quoteReference` in quote responses.
- These notes describe the present behavior of the generated code and should be folded into the business specification when they are confirmed as intended behavior.

## Out of Scope (v1)
- Customer-specific contract rates / negotiated tariffs
- Multi-currency conversion
- Spot rate market integration
- Automatic rate management / revenue optimization
