# Component: Quotes Service

## Purpose
Calculates and returns freight prices for a given schedule, equipment selection, and cargo weight.
Provides a quoted price that can be referenced when placing a booking.

## Responsibilities
- Accept a rate request (schedule + equipment + weight)
- Apply freight rates and surcharges to produce a total price
- Store quotes with a validity period so they can be referenced by Booking
- Persist durable quote lifecycle events for downstream consumers through an outbox table
- Return itemised price breakdown
- Provide internal admin workflows for managed rate-table and surcharge-rule changes
- Require platform bearer authorization for protected operational routes while keeping public quote request/read behavior unauthenticated

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /quotes | Request a new quote |
| POST | /quotes/{id}/reprice | Reprice a stored quote and persist variance against the original |
| POST | /quotes/{id}/approval-decisions | Approve or reject a quote currently held for manual approval |
| POST | /quotes/{id}/revocations | Void an issued or approved quote so it can no longer be booked |
| POST | /quotes/coverage/validate | Validate rate coverage for a route, departure date, and equipment selection |
| POST | /quotes/equipment-availability/plan | Check a requested equipment mix against an Equipments-style availability snapshot and return substitution suggestions |
| GET | /quotes/{id} | Retrieve a quote by internal ID or public quote reference |
| GET | /quotes/{id}/explain | Return stored pricing explainability for a quote |
| GET | /quotes/{id}/bookability | Validate whether a stored quote is still usable for booking |
| GET | /quotes/reference/{quoteReference} | Retrieve a quote by human-readable quote reference |
| POST | /admin/rate-tables | Create a draft managed rate-table version |
| PATCH | /admin/rate-tables/{id} | Update a draft managed rate-table version |
| POST | /admin/rate-tables/{id}/activate | Activate a managed rate-table version |
| POST | /admin/surcharge-rules | Create a draft managed surcharge-rule version |
| PATCH | /admin/surcharge-rules/{id} | Update a draft managed surcharge-rule version |
| POST | /admin/surcharge-rules/{id}/activate | Activate a managed surcharge-rule version |
| GET | /admin/commercial-change-events | List managed commercial data audit events |
| GET | /admin/outbox-events | List durable quote and managed-commercial outbox events |
| POST | /admin/outbox-consumers/{consumerName}/replay | Replay ordered outbox events for a named consumer checkpoint |
| POST | /admin/impact-analyses | Persist a schedule- or contract-change impact summary |
| GET | /admin/impact-analyses/{id} | Retrieve a recorded impact-analysis run |
| POST | /admin/quote-preview | Preview quote pricing with draft managed commercial rows |
| GET | /admin/service-connections/equipments | Check configured Equipments service health connectivity |

## Authentication And Authorization

Quotes follows the platform bearer-token shape already implemented by the
Equipments service:

- JWT algorithm: `HS256`
- issuer environment variable: `AUTH_JWT_ISSUER`, default `platform-auth`
- audience environment variable: `AUTH_JWT_AUDIENCE`, default `quotes-service`
- signing secret environment variable: `AUTH_JWT_SECRET`, default
  `quotes-dev-secret` for local development only
- scopes claim: space-delimited `scope` string

Public quote request and read endpoints remain unauthenticated so the customer
portal and Booking-facing lookup flows continue to work while the API gateway
contract evolves.

Protected operational routes require these scopes:

| Scope | Required for |
|-------|--------------|
| `quotes:approve` | `POST /quotes/{id}/approval-decisions` |
| `quotes:admin` | All `/admin/*` routes, `POST /quotes/{id}/reprice`, and `POST /quotes/{id}/revocations` |

When a protected request includes both a valid bearer token and `X-Actor`, the
service records `X-Actor` as the business actor for audit compatibility. When
`X-Actor` is omitted, the token subject is recorded as the actor. Missing,
malformed, expired, wrong-issuer, wrong-audience, or incorrectly signed bearer
tokens return `401`. Valid tokens without the required scope return `403`.

## 2026-05-19 Cross-Repo Auth/RBAC Deployment Plan

This plan turns the 2026-05-19 AgenticFunProject remote discovery into a
reviewable Quotes implementation sequence. It is intentionally written before
runtime auth changes so the token contract, RBAC compatibility decisions,
gateway behavior, deployment checks, and downstream boundaries are agreed first.

### Token issuer, audience, and source

Protected Quotes routes continue to validate HS256 platform tokens with:

- `AUTH_JWT_ISSUER`, default `platform-auth`
- `AUTH_JWT_AUDIENCE`, default `quotes-service`
- `AUTH_JWT_SECRET`, supplied from secret material outside local development
- a space-delimited `scope` claim

Quotes should accept Users-issued or gateway-issued Quotes-audience tokens only
when the token validates against the configured issuer, audience, expiry, and
signature. Users currently defaults issued tokens to the Equipments audience, so
any Users-issued Quotes token must be deliberately configured with
`AUTH_JWT_AUDIENCE=quotes-service` or an equivalent future multi-audience
contract. The web-page `/api/auth/quotes-token` helper is a local developer
source, not production identity-provider behavior.

### Quotes scopes

Quotes keeps the service-specific scopes already documented:

- `quotes:admin` for all `/admin/*` routes, `POST /quotes/{id}/reprice`, and
  `POST /quotes/{id}/revocations`
- `quotes:approve` for `POST /quotes/{id}/approval-decisions`

Public quote request/read endpoints remain unauthenticated. Callers must not
attach bearer tokens to public quote request or read calls unless a future
gateway route intentionally exposes a protected Quotes operation. Protected
gateway work must not attach bearer tokens to public quote request or read
calls.

The gateway must not attach bearer tokens to public quote request or read calls.

### Role compatibility decision

`role=admin` compatibility remains an open decision. Equipments accepts the
`admin` role as a privileged shortcut after normal token validation. Quotes
currently authorizes by `quotes:admin` and `quotes:approve` scopes only. The
next implementation must choose one of these explicit outcomes before code
changes:

1. Keep Quotes scope-only authorization and require Users or the gateway to mint
   Quotes-specific scopes.
2. Accept `role=admin` for protected Quotes routes, with tests proving that the
   role never bypasses issuer, audience, expiry, or signature validation.
3. Accept `role=admin` only for `quotes:admin` operations while keeping
   approval decisions scoped by `quotes:approve`.

### Protected-route status behavior

Protected routes must return `401` when the bearer token is missing, malformed,
expired, signed with the wrong secret, uses the wrong issuer, or uses the wrong
audience. Protected routes must return `403` when the token is valid but lacks
the required Quotes scope or any accepted role compatibility decided above.

### Web-page token propagation boundaries

The web-page gateway can mint a local `/api/auth/quotes-token` token for manual
operator and demo flows. The browser API helper currently attaches bearer
tokens only to `/api/equipment`, and that boundary should remain intact for
customer quote creation and quote lookup. If the UI later exposes protected
Quotes admin or approval operations, token attachment should be limited to those
explicit protected paths and should not turn public quote workflows into
authenticated workflows.

### Azure deployment verification

Deploy to Azure only after the target environment has explicit platform auth
settings:

- `AUTH_JWT_ISSUER` set to the accepted platform issuer
- `AUTH_JWT_AUDIENCE` set to `quotes-service`
- `AUTH_JWT_SECRET` supplied from GitHub secret material or a secret manager,
  not from `quotes-dev-secret`

Deployment sign-off should verify `/health`, one unauthenticated public quote
read or request flow, one protected `quotes:admin` route, and one protected
`quotes:approve` route with a valid Quotes-audience token. It should also
verify that an Equipments-audience token is rejected by Quotes with `401`.

### Booking and Equipments integration boundaries

Booking should continue using public Quotes validation and lookup behavior for
quote bookability and pricing provenance until a dedicated service-to-service
contract is accepted. Booking must not forward a customer's bearer token to
Quotes public endpoints by default.

Equipments remains a separate protected service. Quotes only calls Equipments
through the configured `/admin/service-connections/equipments` diagnostic today;
that diagnostic requires `quotes:admin` and must not accept caller-supplied
target URLs.

### Remaining open decisions

- Whether Quotes should accept `role=admin`, and for which protected actions.
- Whether Users will mint first-class Quotes-audience tokens or whether the
  gateway remains the local token source for demo-only protected Quotes flows.
- Whether web-page will ever expose protected Quotes admin or approval actions.
- Whether near-term deployment remains Azure App Service for Quotes while Users
  and Equipments document Container Apps, or whether the town converges on
  Container Apps.
- When Booking moves from public quote validation and lookup calls to any
  authenticated service-to-service Quotes contract.

## Service Connectivity Diagnostics

`GET /admin/service-connections/equipments` lets operators test whether the
Quotes runtime can reach the configured Equipments service health endpoint. The
endpoint requires `quotes:admin`, uses only configured target URLs, and does not
accept arbitrary URLs in request parameters.

Configuration:

- `EQUIPMENTS_SERVICE_URL`: Equipments service base URL.
- `EQUIPMENTS_HEALTH_PATH`: health path, default `/health`.
- `EQUIPMENTS_CONNECTIVITY_TIMEOUT_SECONDS`: request timeout, default `3`, max
  `30`.

Response statuses:

| Status | Meaning |
|--------|---------|
| `ok` | `EQUIPMENTS_SERVICE_URL` is configured and the health endpoint returned a 2xx status |
| `unhealthy` | the service is configured but the health call returned non-2xx or failed before a healthy response |
| `not_configured` | `EQUIPMENTS_SERVICE_URL` is missing or blank |

Example response:

```json
{
  "service": "equipments",
  "configured": true,
  "ok": true,
  "status": "ok",
  "baseUrl": "https://equipments.example.com",
  "healthPath": "/health",
  "httpStatus": 200
}
```

### POST /quotes - Request Body
```json
{
  "scheduleId": "string",
  "customerId": "string",
  "accountId": "string",
  "currency": "EUR",
  "pricingModeHint": "MARKET",
  "includeAlternativeOptions": true,
  "maxAlternativeOptions": 1,
  "equipment": [
    { "type": "20FT", "quantity": 2 },
    { "type": "40FT", "quantity": 1 }
  ],
  "cargoWeightKg": 18000
}
```

- `customerId` and `accountId` are optional request context fields.
- `currency` is optional and defaults to `USD`.
- `pricingModeHint` is optional and can be `AUTO`, `PUBLIC_TARIFF`, `CONTRACT`, or `MARKET`.
- `includeAlternativeOptions` is optional and defaults to `false`; when `true`, the response includes a primary option plus ordered alternatives.
- `maxAlternativeOptions` is optional, accepts values from `1` through `10`, and only bounds the ordered alternatives returned when `includeAlternativeOptions=true`.
- When both are present, account-specific contracts take precedence over customer-level contracts.
- If no matching contract covers the request, the service falls back to `PUBLIC_TARIFF` pricing.
- `pricingModeHint=MARKET` asks the service to use approved market-rate snapshots when they fully cover the request; otherwise the service falls back to contract or public tariff pricing and persists that fallback decision.
- The commercial source amount is still resolved in governed `USD` and then converted into the requested display currency.

### POST /quotes - Response
```json
{
  "quoteReference": "QTE-2026-00108",
  "id": "53c362b2-1229-4ea5-a24a-9891fb1f509d",
  "validUntil": "2026-04-07T23:59:59Z",
  "currency": "EUR",
  "sourceCurrency": "USD",
  "responseCurrency": "EUR",
  "fx": {
    "provider": "seeded-governed-fx",
    "baseCurrency": "USD",
    "quoteCurrency": "EUR",
    "rate": 0.92,
    "observedAt": "2026-05-06T00:00:00+00:00",
    "referenceDataVersion": "seed-fx-2026-05-06"
  },
  "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
  "lineItems": [
    { "description": "Ocean Freight - 20FT x 2", "amount": 1748.00 },
    { "description": "Ocean Freight - 40FT x 1", "amount": 1288.00 },
    { "description": "Bunker Adjustment Factor (BAF)", "amount": 220.80 },
    { "description": "Port Congestion Surcharge - Destination USNYC", "amount": 414.00 },
    { "description": "Peak Season Surcharge", "amount": 331.20 }
  ],
  "sourceTotalAmount": 4350.00,
  "totalAmount": 4002.00
}
```

### POST /quotes/{id}/reprice - Request Body
```json
{
  "trigger": "COMMERCIAL_REFRESH"
}
```

### POST /quotes/{id}/reprice - Response
```json
{
  "id": "6f8b08fe-57cf-4c6d-b29c-5b0e2e10fd8a",
  "quoteReference": "QTE-2026-00109",
  "repricedFromQuoteId": "53c362b2-1229-4ea5-a24a-9891fb1f509d",
  "repricedFromQuoteReference": "QTE-2026-00108",
  "repricingTrigger": "COMMERCIAL_REFRESH",
  "pricingBasis": "PUBLIC_TARIFF",
  "currency": "EUR",
  "sourceCurrency": "USD",
  "responseCurrency": "EUR",
  "varianceSummary": {
    "direction": "HIGHER",
    "totalAmount": {
      "original": 1196.00,
      "repriced": 1444.00,
      "delta": 248.00,
      "changed": true
    },
    "baseRate": {
      "original": 950.00,
      "repriced": 1110.00,
      "delta": 160.00,
      "changed": true
    },
    "surcharges": {
      "original": 350.00,
      "repriced": 410.00,
      "delta": 60.00,
      "changed": true
    },
    "fx": {
      "changed": true,
      "original": { "rate": 0.92 },
      "repriced": { "rate": 0.95 }
    },
    "marketInputs": {
      "changed": false,
      "original": {
        "pricingBasis": "PUBLIC_TARIFF",
        "marketSource": null,
        "marketRateSnapshotIds": []
      },
      "repriced": {
        "pricingBasis": "PUBLIC_TARIFF",
        "marketSource": null,
        "marketRateSnapshotIds": []
      }
    },
    "optimizationInputs": {
      "changed": false,
      "original": { "pricingModeHint": "AUTO" },
      "repriced": { "pricingModeHint": "AUTO" }
    }
  }
}
```

### POST /quotes/{id}/revocations - Request Body
```json
{
  "reason": "Customer requested replacement quote after scope changed."
}
```

### POST /quotes/{id}/revocations - Response
```json
{
  "id": "53c362b2-1229-4ea5-a24a-9891fb1f509d",
  "quoteReference": "QTE-2026-00108",
  "lifecycleState": "VOID",
  "pricingBasis": "PUBLIC_TARIFF",
  "pricingProvenance": {
    "pricingBasis": "PUBLIC_TARIFF",
    "referenceDataVersion": "seed-2026-04-01",
    "sourceCurrency": "USD",
    "responseCurrency": "USD"
  },
  "sourceTotalAmount": 1960.00,
  "totalAmount": 1960.00,
  "validUntil": "2026-04-07T23:59:59Z"
}
```

- The `{id}` path parameter accepts either the stored quote UUID or the public
  `quoteReference`.
- The endpoint requires a bearer token with `quotes:admin`.
- `X-Actor` is optional audit metadata; when it is absent, the token subject is
  recorded as the revoking actor.
- Only `ISSUED` and `APPROVED` quotes that are unexpired and not booked can be
  revoked.
- Expired, rejected, already void/revoked, booked, or pending-approval quotes
  return `409` without writing a `quote.revoked` event.
- Successful revocation changes the quote lifecycle to `VOID`, preserves the
  stored pricing/provenance snapshots, and appends a durable `quote.revoked`
  outbox event with quote identifiers, actor, reason, lifecycle state,
  commercial snapshot, and pricing provenance.

### POST /quotes/coverage/validate - Request Body
```json
{
  "originPort": "NLRTM",
  "destinationPort": "USNYC",
  "departureDate": "2026-08-18",
  "equipment": [
    { "type": "20FT", "quantity": 2 },
    { "type": "40FT_HC", "quantity": 1 }
  ]
}
```

### POST /quotes/coverage/validate - Response
```json
{
  "covered": true,
  "reason": "RATE_AVAILABLE",
  "pricingBasis": "PUBLIC_TARIFF",
  "referenceDataVersion": "seed-2026-04-01",
  "route": {
    "originPort": "NLRTM",
    "destinationPort": "USNYC",
    "departureDate": "2026-08-18"
  },
  "coverage": [
    {
      "equipmentType": "20FT",
      "quantity": 2,
      "covered": true,
      "rateTableId": "<rate-table-id>",
      "validFrom": "2026-04-01",
      "validTo": "2026-12-31"
    }
  ],
  "uncoveredEquipment": []
}
```

### POST /quotes/equipment-availability/plan - Request Body
```json
{
  "depotCode": "CNSHA-01",
  "equipment": [
    { "type": "40FT", "quantity": 2 }
  ],
  "availability": [
    { "equipmentType": "40FT", "availableCount": 1, "depotCode": "CNSHA-01" },
    { "equipmentType": "40FT_HC", "availableCount": 3, "depotCode": "CNSHA-01" }
  ],
  "substitutions": [
    {
      "requestedType": "40FT",
      "substituteType": "40FT_HC",
      "priority": 1,
      "reason": "High-cube unit is acceptable for standard 40-foot dry demand"
    }
  ]
}
```

- This endpoint is a quote-planning helper for the Booking and Equipments
  business boundary discovered from the sibling repositories.
- The `availability` array intentionally uses the Equipments `GET /availability`
  response shape: `equipmentType`, `availableCount`, and `depotCode`.
- The endpoint does not reserve equipment, mutate quote state, or call
  Equipments. Callers provide the availability snapshot they want Quotes to
  evaluate.
- `substitutions` is an explicit policy input. Quotes does not infer hidden
  compatibility rules from equipment names.
- If `depotCode` is supplied, only availability rows for that depot contribute
  to the plan.
- The request accepts both the Quotes internal high-cube code `40FT_HC` and the
  Equipments/Booking external code `40HC`; responses use the Quotes canonical
  code `40FT_HC`.

### POST /quotes/equipment-availability/plan - Response
```json
{
  "status": "AVAILABLE_WITH_SUBSTITUTIONS",
  "available": true,
  "depotCode": "CNSHA-01",
  "equipment": [
    {
      "type": "40FT",
      "requestedQuantity": 2,
      "availableCount": 1,
      "directCoveredQuantity": 1,
      "shortageQuantity": 1,
      "status": "SHORTAGE"
    }
  ],
  "substitutions": [
    {
      "requestedType": "40FT",
      "substituteType": "40FT_HC",
      "priority": 1,
      "reason": "High-cube unit is acceptable for standard 40-foot dry demand",
      "availableCount": 3,
      "quantityCovered": 1
    }
  ],
  "uncoveredEquipment": []
}
```

Response statuses:

| Status | Meaning |
|--------|---------|
| `AVAILABLE` | Every requested equipment line is directly covered by the supplied availability snapshot |
| `AVAILABLE_WITH_SUBSTITUTIONS` | Direct stock is short, but explicit substitution policy rows cover the remaining shortage |
| `SHORTAGE` | Neither direct stock nor explicit substitutions fully cover the request |

### GET /quotes/{id} - Response
```json
{
  "id": "53c362b2-1229-4ea5-a24a-9891fb1f509d",
  "quoteReference": "QTE-2026-00108",
  "lifecycleState": "ISSUED",
  "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
  "scheduleSnapshot": {
    "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
    "originPort": "NLRTM",
    "destinationPort": "USNYC",
    "departureDate": "2026-08-18"
  },
  "equipment": [
    { "type": "20FT", "quantity": 2 }
  ],
  "cargoWeightKg": 18000,
  "currency": "EUR",
  "sourceCurrency": "USD",
  "responseCurrency": "EUR",
  "fx": {
    "provider": "seeded-governed-fx",
    "baseCurrency": "USD",
    "quoteCurrency": "EUR",
    "rate": 0.92,
    "observedAt": "2026-05-06T00:00:00+00:00",
    "referenceDataVersion": "seed-fx-2026-05-06"
  },
  "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
  "pricingBasis": "PUBLIC_TARIFF",
  "pricingProvenance": {
    "pricingBasis": "PUBLIC_TARIFF",
    "referenceDataVersion": "seed-2026-04-01",
    "sourceCurrency": "USD",
    "responseCurrency": "EUR",
    "sourceTotalAmount": 1960,
    "currencyConversion": {
      "provider": "seeded-governed-fx",
      "baseCurrency": "USD",
      "quoteCurrency": "EUR",
      "rate": 0.92,
      "observedAt": "2026-05-06T00:00:00+00:00",
      "referenceDataVersion": "seed-fx-2026-05-06",
      "roundingPolicy": "LINE_ITEM_HALF_UP_2DP",
      "conversionLevel": "LINE_ITEM"
    },
    "baseRateRules": [
      {
        "rateTableId": "rate-20ft-nlrtm-usnyc",
        "equipmentType": "20FT",
        "quantity": 2,
        "currency": "USD",
        "unitAmount": 950,
        "totalAmount": 1900,
        "validFrom": "2026-04-01",
        "validTo": "2026-12-31"
      }
    ],
    "appliedSurchargeRules": [
      {
        "surchargeRuleId": "rule-baf",
        "surchargeType": "BAF",
        "description": "Bunker Adjustment Factor (BAF)",
        "currency": "USD",
        "unitAmount": 80,
        "totalAmount": 160,
        "portCode": null,
        "portScope": null,
        "weightThresholdKgPerTeu": null,
        "validFrom": null,
        "validTo": null
      }
    ]
  },
  "customerId": null,
  "accountId": null,
  "contractId": null,
  "idempotencyKey": null,
  "lineItems": [
    { "description": "Ocean Freight - 20FT x 2", "amount": 1656.00 },
    { "description": "Bunker Adjustment Factor (BAF)", "amount": 147.20 }
  ],
  "sourceTotalAmount": 1960.00,
  "totalAmount": 1803.20,
  "validUntil": "2026-04-07T23:59:59Z",
  "createdAt": "2026-04-01T09:30:00Z"
}
```

### GET /quotes/{id}/bookability - Response
```json
{
  "quoteId": "QTE-2026-00108",
  "bookable": true,
  "status": "ACTIVE",
  "reason": "VALIDITY_WINDOW_OPEN",
  "expired": false,
  "validUntil": "2026-04-07T23:59:59Z"
}
```

Revoked quotes return:

```json
{
  "quoteId": "QTE-2026-00108",
  "bookable": false,
  "status": "VOID",
  "reason": "QUOTE_REVOKED",
  "expired": false,
  "validUntil": "2026-04-07T23:59:59Z"
}
```

### POST /admin/rate-tables - Request Body
```json
{
  "originPort": "NLRTM",
  "destinationPort": "USNYC",
  "equipmentType": "20FT",
  "baseRateUsd": 1000,
  "validFrom": "2026-04-01",
  "validTo": "2026-12-31"
}
```

### POST /admin/rate-tables - Response
```json
{
  "id": "<uuid>",
  "originPort": "NLRTM",
  "destinationPort": "USNYC",
  "equipmentType": "20FT",
  "baseRateUsd": 1000,
  "validFrom": "2026-04-01",
  "validTo": "2026-12-31",
  "version": 2,
  "isActive": false,
  "createdBy": "pricing.ops@quotes",
  "updatedBy": "pricing.ops@quotes",
  "activatedBy": null,
  "createdAt": "2026-05-06T14:00:00+00:00",
  "updatedAt": "2026-05-06T14:00:00+00:00",
  "activatedAt": null
}
```

### POST /admin/surcharge-rules - Request Body
```json
{
  "surchargeType": "PORT_CONGESTION",
  "description": "Port Congestion Surcharge - Destination USNYC",
  "amountUsd": 175,
  "currency": "USD",
  "portCode": "USNYC",
  "portScope": "DESTINATION"
}
```

### POST /admin/surcharge-rules - Response
```json
{
  "id": "<uuid>",
  "surchargeType": "PORT_CONGESTION",
  "description": "Port Congestion Surcharge - Destination USNYC",
  "amountUsd": 175,
  "currency": "USD",
  "portCode": "USNYC",
  "portScope": "DESTINATION",
  "weightThresholdKgPerTeu": null,
  "validFrom": null,
  "validTo": null,
  "version": 2,
  "isActive": false,
  "createdBy": "pricing.ops@quotes",
  "updatedBy": "pricing.ops@quotes",
  "activatedBy": null,
  "createdAt": "2026-05-06T14:00:00+00:00",
  "updatedAt": "2026-05-06T14:00:00+00:00",
  "activatedAt": null
}
```

### GET /quotes/{id}
- The `{id}` path parameter accepts either the stored quote UUID or the public `quoteReference`.
- This endpoint is the primary lookup path used by the current implementation.

### GET /quotes/{id}/explain
- The `{id}` path parameter accepts either the stored quote UUID or the public `quoteReference`.
- This endpoint returns the stored pricing basis, selected market source when present, persisted optimization trace, and the full stored pricing provenance used to create the quote.

### POST /quotes/{id}/approval-decisions
- The `{id}` path parameter accepts either the stored quote UUID or the public `quoteReference`.
- This endpoint accepts an approval decision for quotes currently in `PENDING_APPROVAL` and returns `409` for quotes in any other lifecycle state.
- Decisions require a bearer token with `quotes:approve`, persist the approver decision snapshot on the quote, and append either a quote-approved or quote-rejected outbox event. `X-Actor` is optional audit metadata; when it is absent, the token subject is recorded as the actor.

### POST /quotes/{id}/revocations
- The `{id}` path parameter accepts either the stored quote UUID or the public `quoteReference`.
- This endpoint requires a bearer token with `quotes:admin`.
- The request carries a short `reason` string that is persisted in the
  `quote.revoked` outbox event with the revoking actor.
- Revocation is allowed only for unexpired `ISSUED` or `APPROVED` quotes that
  have not been booked. Expired, rejected, void/revoked, booked, and
  pending-approval quotes return `409`.
- Revoked quotes return `bookable=false`, `status=VOID`, and
  `reason=QUOTE_REVOKED` from `GET /quotes/{id}/bookability`.

### POST /quotes/{id}/reprice
- The `{id}` path parameter accepts either the stored quote UUID or the public `quoteReference`.
- This endpoint requires a bearer token with `quotes:admin`.
- Repricing preserves the original quote unchanged and persists a distinct quote record with a durable link back to the source quote.

### POST /quotes/coverage/validate
- This endpoint accepts direct route attributes instead of a `scheduleId` so clients can validate commercial data coverage before attempting a quote request.
- `covered` is `true` only when every requested equipment selection has an effective public tariff rate for the submitted route and departure date.
- `uncoveredEquipment` lists the equipment types that would fail commercial quote creation because no effective base rate exists.

### POST /quotes/equipment-availability/plan
- This endpoint evaluates operational equipment availability separately from commercial rate coverage.
- It is stateless: it accepts the requested equipment, a caller-supplied availability snapshot in Equipments style, and optional substitution policy rows; then returns a deterministic plan.
- It does not create quotes, reserve equipment, mark quotes bookable, or replace Booking's final reservation check.
- Availability rows are consumed per equipment type, so the same available substitute units cannot satisfy multiple shortages in one response.
- `40HC` is accepted as an inbound alias for `40FT_HC` to align with the Equipments and Booking API vocabulary while preserving the current Quotes canonical equipment code.

### Multi-currency quote behavior
- Base freight, contracts, and surcharges are currently governed in `USD`.
- `POST /quotes` and `POST /admin/quote-preview` can return a display currency by converting each line item from the governed `USD` source amount using the persisted FX snapshot and `LINE_ITEM_HALF_UP_2DP` rounding policy.
- `currency` remains the display currency on the stored quote; `sourceCurrency` exposes the governed commercial basis.
- `sourceTotalAmount` is the pre-conversion total, while `totalAmount` is the sum of the rounded display-currency line items.
- `pricingProvenance.currencyConversion` records the persisted FX provider, rate, observed timestamp, reference-data version, and conversion level used for reproducibility.

### Admin managed commercial data endpoints
- All `/admin/*` endpoints require a bearer token with `quotes:admin`.
- `X-Actor` is optional audit metadata for write operations; when it is absent, the token subject is recorded as the actor.
- `POST /admin/rate-tables` and `POST /admin/surcharge-rules` create draft versions with `isActive=false`.
- `PATCH /admin/rate-tables/{id}` and `PATCH /admin/surcharge-rules/{id}` only allow draft edits. Active managed rows are immutable; clients must create a new draft version instead.
- `POST /admin/rate-tables/{id}/activate` and `POST /admin/surcharge-rules/{id}/activate` promote the selected draft version and deactivate overlapping active versions for the same commercial scope.
- Every managed commercial create, update, and activate operation appends a durable row to `commercial_change_events` with the actor, action, resource version, and post-change snapshot.
- `GET /admin/commercial-change-events` returns the audit trail and can be filtered by `resourceType` and `resourceId`.
- `GET /admin/outbox-events` returns the current durable event stream with optional aggregate type, aggregate ID, event-type, and publication filters.
- `POST /admin/outbox-consumers/{consumerName}/replay` replays the next ordered outbox batch for a named consumer and advances its checkpoint.
- `POST /admin/impact-analyses` persists a schedule- or contract-change impact summary for the affected quotes.
- `GET /admin/impact-analyses/{id}` returns a previously recorded impact-analysis run.
- `POST /admin/quote-preview` accepts the same shipment request shape as `POST /quotes` plus optional `rateTableIds` and `surchargeRuleIds` to preview explicit draft versions before activation.
- Quote creation and coverage validation read only active managed commercial data.

### GET /quotes/reference/{quoteReference}
- The `{quoteReference}` path parameter is the business-facing quote reference in `QTE-YYYY-NNNNN` format.
- This endpoint returns the same quote payload shape as `GET /quotes/{id}`.

### GET /quotes/{id}/bookability
- The `{id}` path parameter accepts either the internal quote UUID or the public quote reference.
- This endpoint returns booking-specific validity information derived from the stored quote.

## Local Demo Workflow

Use this walkthrough when validating the current service behavior locally or
when integrating a client against the seeded demo data.

### Step 1: Create a quote on a supported seeded schedule

Request:

```json
{
  "scheduleId": "df62a7d2-a45e-4d4d-b3cb-b4af65435274",
  "equipment": [
    { "type": "20FT", "quantity": 1 }
  ],
  "cargoWeightKg": 18000
}
```

Expected result:

- `POST /quotes` returns `201`.
- The payload includes both the internal quote `id` and the public `quoteReference`.
- The quote is priced from seeded `PUBLIC_TARIFF` data and includes the matched surcharge line items for that lane.

### Step 2: Retrieve the stored quote through either lookup path

- Use `GET /quotes/{id}` when the caller stores the internal UUID or when it already has the public quote reference and wants to use the primary lookup path.
- Use `GET /quotes/reference/{quoteReference}` when the client wants an explicit business-facing route for the human-readable identifier.
- Both endpoints return the same stored commercial record, including `scheduleSnapshot`, `pricingBasis`, `pricingProvenance`, `lineItems`, and `validUntil`.

### Step 3: Validate bookability before Booking consumes the quote

- Use `GET /quotes/{id}/bookability` with either the quote UUID or the public `quoteReference`.
- The response returns Booking-oriented validity fields: `bookable`, `status`, `reason`, `expired`, and `validUntil`.
- A quote can be retrievable even when it is no longer bookable; bookability is a separate lifecycle check from quote lookup.

### Step 4: Validate route coverage before pricing

- Use `POST /quotes/coverage/validate` with the requested `originPort`, `destinationPort`, `departureDate`, and equipment selection.
- The response tells the client whether managed public tariff data covers the requested lane before it tries to create a quote.
- This is the recommended preflight path for clients that want a deterministic commercial coverage check without depending on a seeded schedule identifier.

### Step 5: Verify the unsupported-lane validation path

- The seeded schedule `1ce1ab21-9d58-4a6d-b867-afc93098352f` (`BRSSZ -> USLAX`) is intentionally present without a matching effective base-rate row.
- `POST /quotes` for that schedule returns `400` when the request asks for a lane and equipment combination that the service recognizes operationally but cannot price commercially.
- This path is useful for client testing because it proves the difference between "schedule exists" and "schedule is quoteable".

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

### Pricing Basis Semantics
- `PUBLIC_TARIFF` means the quote was priced from this service's stored rate-table and surcharge-rule reference data.
- `CONTRACT` means the quote was priced from stored customer or account contract rules, with explicit precedence and surcharge-waiver metadata captured in `pricingProvenance`.
- `MARKET` means the quote used fully covered approved market-rate snapshots for the base freight component while still applying governed surcharge rules.
- `HYBRID` is reserved for future explicitly approved combinations of pricing sources.
- `pricingBasis` names the commercial mode, while `pricingProvenance` captures the exact stored rule snapshot that mode used.
- `pricingProvenance.baseRateRules[*].rateVersion` identifies the active managed rate-table version used for public tariff pricing.
- `pricingProvenance.appliedSurchargeRules[*].surchargeRuleVersion` identifies the active managed surcharge-rule version used for each applied surcharge.
- `pricingProvenance.marketSource` identifies the approved upstream market source when market pricing wins.
- `pricingProvenance.optimizationTrace` persists the request hint, fallback basis, evaluated market signals, and the final pricing decision whenever the market/optimization path is exercised.

### Market Pricing and Optimization Rules
- The service only considers market pricing from approved `market_rate_snapshots` that fully cover every requested equipment type for the schedule lane and departure date.
- `pricingModeHint=MARKET` prefers those approved market snapshots and falls back to contract or public tariff pricing when market coverage is incomplete.
- Without a market hint, the service can still choose `MARKET` when an active pricing strategy version matches at least one stored signal threshold for capacity pressure, utilization, or seasonality.
- The chosen basis and the exact rule path are stored in `optimizationTrace` and are retrievable through `GET /quotes/{id}/explain`.

### Contract Pricing Rules
- Contract matching is deterministic: account-specific contracts win over customer-level contracts for the same lane and departure date.
- A contract must cover every requested equipment type; otherwise the service falls back to public tariff pricing.
- Contracts can waive selected surcharges while still using the same surcharge rule catalog for non-waived items.
- Contract provenance records the matched customer/account context, contract identifier, match type, and waived surcharge types.

## Data Model (Quote)
| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Internal primary key |
| quoteReference | string | Human-readable (QTE-YYYY-NNNNN) |
| lifecycleState | enum | `ISSUED`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`, `BOOKED`, `EXPIRED`, `VOID` |
| scheduleId | UUID | |
| scheduleSnapshot | JSON object | Stored schedule facts used for later validation |
| equipment | JSON array | type + quantity |
| cargoWeightKg | number | |
| currency | string | ISO 4217, default USD |
| pricingBasis | enum | Commercial pricing mode used for the quote |
| marketSource | string nullable | Approved upstream market source when `pricingBasis=MARKET` |
| pricingProvenance | JSON object | Stored matched base-rate and surcharge rules plus reference data version |
| optimizationTrace | JSON object | Stored market/optimization decision path and fallback details |
| idempotencyKey | string nullable | Reserved for request replay handling |
| lineItems | JSON array | description + amount |
| totalAmount | decimal | |
| validUntil | timestamp | |
| createdAt | timestamp | |

## Data Model (Quote Outbox Event)
| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Internal primary key |
| aggregateType | string | Currently `quote` |
| aggregateId | UUID | Internal quote ID |
| eventType | string | Versioned lifecycle event name such as `quote.created`, `quote.expired`, or `quote.revoked` |
| eventVersion | integer | Payload contract version |
| payload | JSON object | Event body including quote identifiers, lifecycle state, schedule snapshot, pricing provenance, and commercial totals |
| occurredAt | timestamp | When the lifecycle event occurred |
| publishedAt | timestamp nullable | Set by a future dispatcher after successful publication |
| publishAttempts | integer | Retry counter for asynchronous dispatch |
| lastError | string nullable | Last publish failure captured by the dispatcher |

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
| version | integer | Monotonic managed version within the same lane and equipment scope |
| isActive | boolean | Only active rows are eligible for quote pricing |
| createdBy | string nullable | Actor from `X-Actor` when created through the admin API |
| updatedBy | string nullable | Last actor to edit the draft or activate it |
| activatedBy | string nullable | Actor who promoted the row into use |
| createdAt | timestamp | Draft creation time |
| updatedAt | timestamp | Last draft edit or activation time |
| activatedAt | timestamp nullable | When the row became active |

## Data Model (Surcharge Rule)
| Field | Type | Notes |
|-------|------|-------|
| id | UUID | |
| surchargeType | enum | BAF, PORT_CONGESTION, HEAVY_CARGO, PEAK_SEASON |
| description | string | Human-readable commercial label |
| amountUSD | decimal | |
| currency | string | ISO 4217 |
| portCode | string nullable | Scope port when relevant |
| portScope | enum nullable | ORIGIN or DESTINATION when relevant |
| weightThresholdKgPerTeu | decimal nullable | Heavy cargo threshold |
| validFrom | date nullable | Effective date start |
| validTo | date nullable | Effective date end |
| version | integer | Monotonic managed version within the same surcharge scope |
| isActive | boolean | Only active rows are eligible for quote pricing |
| createdBy | string nullable | Actor from `X-Actor` when created through the admin API |
| updatedBy | string nullable | Last actor to edit the draft or activate it |
| activatedBy | string nullable | Actor who promoted the row into use |
| createdAt | timestamp | Draft creation time |
| updatedAt | timestamp | Last draft edit or activation time |
| activatedAt | timestamp nullable | When the row became active |

## Data Model (Commercial Change Event)
| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Internal primary key |
| resourceType | enum | `RATE_TABLE` or `SURCHARGE_RULE` |
| resourceId | UUID | Managed row identifier |
| action | enum | `CREATED`, `UPDATED`, or `ACTIVATED` |
| actor | string | `X-Actor` value that made the change |
| resourceVersion | integer | Managed version after the change |
| snapshot | JSON object | Full post-change managed row snapshot |
| occurredAt | timestamp | When the change was recorded |

## Dependencies
| Service | Why |
|---------|-----|
| Schedules API | Validate scheduleId and resolve origin/destination ports |

## Current Integration Boundaries
- `Schedules API` is the only explicitly documented external dependency in this specification.
- In the current implementation, `Schedules API` sits behind a `ScheduleProvider` abstraction backed by a local in-memory schedule stub keyed by `scheduleId`.
- Equipment data is currently modeled inside this service through request payloads, supported equipment types, TEU conversion rules, and seeded rate data.
- Booking is currently a downstream consumer of quotes rather than an active runtime dependency. The service stores quotes with validity so Booking can reference them later.
- The frontend is expected to consume the HTTP API exposed by this service. There is no frontend-specific integration layer in this repository yet.
- System-level repository boundaries, town topology, and architecture-state assumptions are tracked separately in `specification/system-architecture.md` so the service contract and the broader workspace model can evolve without drifting apart.

## Executable Scenarios
- Human-readable Gherkin scenarios for quote service behavior and documented integration boundaries live in `specification/features/`, with one tracked `.feature` file per scenario.
- The scenario-to-binding coverage matrix lives in `specification/quote-scenarios.md` and is checked against the ordered feature files and binding YAML.
- Matching executable service coverage lives in `tests/test_quotes_api.py`; documentation-only boundary guardrails live in `tests/test_documentation.py`.
- Repository landscape and broader architecture-state notes live in `specification/system-architecture.md`, not in the quote scenario catalog.

## Current Implementation Notes
- `POST /quotes` returns the commercial quote payload: `id`, `quoteReference`, `validUntil`, `currency`, `lineItems`, and `totalAmount`.
- `GET /quotes/{id}` accepts either the internal quote UUID or the human-readable `quoteReference` returned during quote creation and returns the stored record, including both identifiers.
- `GET /quotes/reference/{quoteReference}` remains available as an explicit business-facing lookup path for the human-readable quote reference.
- `GET /quotes/{id}/bookability` accepts the same identifiers as quote lookup and returns Booking-focused validation fields: `bookable`, `status`, `reason`, `expired`, and `validUntil`.
- Quote references are generated sequentially within the current UTC year using the `QTE-YYYY-NNNNN` format.
- A schedule lookup and a quoteable lane are not the same thing in the current implementation: a known `scheduleId` can still return `400` when no effective base rate exists for the route, equipment, and departure date.
- Quote lifecycle state is persisted on the quote row and synchronized with `validUntil` when a quote is read after expiry.
- Quote reads persist the commercial mode as `pricingBasis` and return the stored `pricingProvenance` snapshot used to explain the amount later.
- The current implementation versions seeded tariff and surcharge reference data as `seed-2026-04-01` inside `pricingProvenance.referenceDataVersion`.
- The current implementation protects all `/admin/*` endpoints, `POST /quotes/{id}/reprice`, and `POST /quotes/{id}/revocations` with `quotes:admin`.
- The current implementation exposes internal admin endpoints for managed rate-table and surcharge-rule draft creation, draft update, and activation.
- Active managed rate-table and surcharge-rule rows are the only rows used during quote pricing; drafts are inert until explicitly activated.
- Public tariff provenance now records the active `rateVersion` and `surchargeRuleVersion` selected for the quote so later support workflows can explain which managed commercial change produced the amount.
- The current implementation records managed commercial create, update, and activate actions in `commercial_change_events` so support and finance workflows can reconstruct the audit trail.
- The current implementation also publishes those managed commercial changes into `outbox_events` as stable `rate.updated` and `surcharge.updated` events, with the specific commercial action carried in the payload.
- The current implementation exposes `POST /admin/quote-preview` so commercial operators can preview quote pricing with explicit draft rate-table and surcharge-rule versions before activation.
- Quote lifecycle changes are written to `outbox_events` in the same transaction as the quote write that caused them.
- The current implementation emits `quote.created` when a quote is created, `quote.expired` the first time an issued quote is observed past `validUntil`, and `quote.revoked` when an operator voids an issued or approved quote; all quote lifecycle event payloads include the stored pricing provenance snapshot.
- Outbox replay is checkpointed per named consumer in `outbox_consumer_checkpoints`, which lets downstream read models rebuild deterministically without a broker.
- Schedule- and contract-change impact workflows persist their results in `impact_analysis_runs` so operators can inspect which stored quotes would need downstream attention.
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

## Operational Follow-Ups

The product roadmap work through Phase 6 is complete. Remaining follow-up work
is operational and should not change the existing quote contract unless a new
feature bead explicitly requires it.

- `qu-bqa` tracks stabilization of quotes verification runtime prerequisites.
- The main remaining gap is environment consistency across local rig and
  refinery execution: `python3-venv`, `ensurepip`, `pip`, and `pytest` must be
  available without ad hoc repair.
- Follow-up implementation should preserve the existing API/spec behavior and
  focus on making verification reproducible for merge gates and local debug
  sessions.
- The canonical bootstrap path should live in-repo so local verification and
  merge gates exercise the same setup logic.

### Verification Prerequisites

The quotes service currently expects a Python environment capable of running the
repo test suite from a virtual environment.

- `python3 -m venv .venv` must succeed.
- The resulting environment must provide `pip`.
- The environment must be able to install the project's dev dependencies.
- Refinery and local rig verification should run the same pytest command set
  without environment-specific branching.
- Bootstrap should fail fast with an actionable message when `venv` or
  `ensurepip` support is missing from the runtime.

Intended verification flow:

```bash
./scripts/bootstrap-venv.sh
./scripts/verify.sh
```

## Next Feature Candidates

These are intentionally phrased as future implementation slices. They are not
part of the completed roadmap above, but they extend the same quote domain and
should be paired with executable Gherkin scenarios when implemented.

### Quote repricing and variance explanation

#### Business goal
- Allow a client or downstream operator to reprice an existing quote request
  against newer commercial data while preserving the original quote snapshot.

#### Domain behavior
- Repricing is a derived commercial action over a previously issued or expired
  quote; it does not mutate the original record in place.
- The repriced quote should inherit the original shipment inputs unless an
  explicit future feature introduces controlled input edits.
- A repriced quote should keep a durable backward link to the source quote so
  support, booking, and analytics can traverse the quote lineage.
- Repricing should be allowed for both customer-visible quote refreshes and
  internal operator workflows such as schedule-change impact review.

#### Required inputs
- A stored quote identifier.
- A repricing trigger such as customer request, schedule change, validity
  expiry, or commercial refresh.
- The currently active pricing data and rule snapshots.

#### Decision logic
1. Load the original stored quote request and provenance snapshot.
2. Re-run pricing against the latest approved commercial data.
3. Preserve the original quote unchanged and persist a distinct repriced quote
   result.
4. Compute a structured variance summary across base rate, surcharges, FX,
   market inputs, and optimization adjustments.
5. Expose whether the repriced result is higher, lower, or unchanged relative
   to the original quote.

#### Lifecycle and state expectations
- The original quote keeps its existing lifecycle state and provenance snapshot.
- The repriced quote is stored as a new quote record with its own identifier,
  validity window, and explainability payload.
- The link between the original and repriced quote should be first-class data,
  not inferred later from event history.
- If the source quote is no longer bookable, the repriced quote can still be
  issued as a fresh bookable offer when the new commercial basis is valid.

#### API implications
- `POST /quotes/{id}/reprice` should remain idempotent only when the same
  idempotency key and trigger context are reused; otherwise repeated repricing
  requests may intentionally create separate repriced records.
- The response should expose the original and repriced identifiers, the
  repricing trigger, the selected pricing basis, and a machine-readable
  variance summary.
- `GET /quotes/{id}` and `GET /quotes/{id}/explain` should let internal clients
  discover whether a quote was repriced from an earlier quote and, if so, which
  quote it supersedes.

#### Provenance and audit expectations
- Both the original and repriced quote must persist their own complete
  commercial provenance snapshots.
- The repriced quote should capture which trigger initiated repricing and which
  commercial reference-data versions were used.
- Variance summaries should be reproducible from stored snapshots rather than
  recalculated from mutable current rules.
- Quote lifecycle and repricing events should distinguish between quote
  creation, repricing request, repriced result creation, and any later expiry.

#### Operational constraints
- Repricing should be safe to run asynchronously for large backfills while
  still returning deterministic results per selected snapshot.
- The service should protect against repricing loops, such as repeatedly
  repricing the same quote lineage without operator intent.
- Support tooling should be able to filter repriced quotes separately from
  first-issue quotes when investigating customer disputes.

#### Expected outcomes
- Support and Booking should be able to explain why a quote changed.
- The service should preserve both the original and repriced commercial basis.
- Repricing should remain deterministic for the selected reference snapshots.

### Multi-option quote responses

#### Business goal
- Allow a single quote request to return multiple commercial options such as
  cheapest, fastest, or contract-preferred choices without requiring multiple
  API round trips.

#### Domain behavior
- Each returned option represents a commercially distinct shipment choice with
  its own schedule or service attributes, price, and bookability basis.
- The service should declare one option as the canonical primary response while
  still retaining the ordering rationale for alternatives.
- Options should be comparable within one response, but a client must still be
  able to book a specific option without ambiguity about which priced offer was
  selected.

#### Required inputs
- A quote request that may permit more than one eligible schedule or service
  option.
- A documented option ranking policy.
- Limits on how many options the service returns.

#### Decision logic
1. Resolve all commercially eligible service options for the request.
2. Price each option independently using the same provenance rules used for a
   single quote.
3. Rank options using stable selection criteria.
4. Return a canonical primary option plus an ordered list of alternatives.
5. Persist enough provenance so later booking can confirm which option was
   chosen.

#### Lifecycle and state expectations
- A multi-option quote request may persist either one aggregate quote record
  with child options or a set of linked quote records; whichever model is used,
  the chosen booking path must be explicit and durable.
- Unselected alternatives should remain referenceable until quote expiry so
  support can explain which option the customer accepted or declined.
- If one option becomes unavailable before booking, the service should be able
  to mark only that option unavailable without corrupting sibling options.

#### API implications
- `POST /quotes` accepts `includeAlternativeOptions=true` to opt into
  alternative options and optional `maxAlternativeOptions` from `1` through
  `10` to bound the number of ordered alternatives.
- Omitting `maxAlternativeOptions` preserves the full current alternative list,
  and sending it without `includeAlternativeOptions=true` does not add an
  `options` object to the normal quote response.
- The response should expose ranking metadata such as `rank`, `selectionReason`,
  or `primary=true` so clients do not reverse-engineer business ordering from
  array position alone.
- Stable Booking-facing option identifiers remain future work; current returned
  options are response-local priced alternatives.

#### Provenance and audit expectations
- Every option should persist its own pricing provenance, explainability data,
  and schedule snapshot.
- The aggregate response should capture which ranking policy and version were
  used to order the options.
- Audit trails should show whether the customer booked the primary option or an
  alternative, because that choice affects later analytics and dispute review.

#### Operational constraints
- Option expansion must be bounded so a broad search does not fan out into an
  unmanageable number of priced combinations.
- Ranking must remain deterministic even if underlying schedule search returns
  candidates in unstable order.
- Downstream consumers should be able to request only the primary option when
  low-latency quoting is more important than alternative discovery.

#### Expected outcomes
- The client can present alternatives without re-querying the pricing service.
- Every option should remain fully explainable and bookable on its own terms.
- The ranking should be reproducible from stored inputs and policy versions.

### Approval-held quotes

#### Business goal
- Support quotes that are commercially valid but require human approval before
  they can be treated as firm customer offers.

#### Domain behavior
- Guardrail failures should not be modeled as pricing errors when the shipment
  is priceable but operationally sensitive.
- A held quote should preserve the exact priced commercial snapshot that was
  reviewed so approvers are deciding on a concrete offer, not a moving target.
- Approval holds should support both synchronous operator review and delayed
  workflow completion without losing customer context.

#### Required inputs
- Approval guardrails such as minimum margin, exceptional surcharge waiver, or
  oversized market deviation thresholds.
- An approval decision model with approver identity and timestamps.

#### Decision logic
1. Price the request normally.
2. Evaluate the result against approval guardrails.
3. If guardrails are exceeded, store the quote in a pending-approval lifecycle
   state instead of issuing it directly.
4. Persist the exact approval reasons and the approver action once a decision is
   made.
5. Allow downstream consumers to distinguish between issued, pending, approved,
   and rejected commercial outcomes.

#### Lifecycle and state expectations
- The lifecycle should distinguish at least `PENDING_APPROVAL`, `APPROVED`,
  `ISSUED`, and `REJECTED` outcomes for held quotes.
- Approval should advance the held quote without recalculating price unless a
  separate explicit reprice or refresh action is requested.
- Rejection should make the quote non-bookable while retaining the full review
  record for audit and customer-service follow-up.
- Expiry policy for held quotes should be explicit: a quote may expire while
  waiting for approval, or approval may be disallowed after the original review
  window closes.

#### API implications
- `POST /quotes/{id}/approval-decisions` is implemented for approving or
  rejecting quotes already held in `PENDING_APPROVAL`.
- Quote lookup and bookability responses should expose hold status and approval
  reasons clearly enough for downstream systems to avoid treating the quote as a
  firm offer.
- Approval decisions require actor identity and accept an optional decision note
  so the audit trail is attributable and support-readable.
- Broader workflow orchestration around who reviews held quotes and when to
  notify them remains future design.

#### Provenance and audit expectations
- The held quote should persist the exact guardrail rules, policy versions, and
  computed threshold breaches that caused the hold.
- Approval or rejection should capture approver identity, timestamp, decision
  rationale, and whether any exception authority was used.
- Outbox events should let dependent systems react differently to pending,
  approved, rejected, and expired-held quotes.

#### Operational constraints
- Approval workflows must tolerate asynchronous human response without losing
  correlation to the original customer request.
- Approval queues should be searchable by age, lane, customer, and guardrail
  type so commercial teams can manage backlog.
- The service should prevent concurrent conflicting approval decisions on the
  same held quote.

#### Expected outcomes
- Risky quotes should not silently flow through as immediately bookable offers.
- The approval trail should be durable and audit-friendly.
- Approved quotes should keep the same commercial snapshot that was reviewed.

### Customer-specific quote validity policies

#### Business goal
- Allow quote validity windows to vary by customer, contract, pricing mode, or
  market volatility instead of using one generic validity rule for all quotes.

#### Domain behavior
- Validity policy resolution should be part of quote creation, not a later
  post-processing step, because `validUntil` affects customer behavior and
  booking guarantees.
- Policies may be derived from layered inputs such as account contract first,
  then customer default, then pricing-mode fallback.
- Highly volatile pricing modes may intentionally receive shorter validity even
  when the commercial amount calculation is otherwise identical to a stable mode.

#### Required inputs
- A validity policy catalog tied to customer/account context and pricing mode.
- Optional volatility or market-freshness signals for shorter-lived quotes.

#### Decision logic
1. Resolve the applicable validity policy during quote creation.
2. Derive `validUntil` from policy rules instead of a single default duration.
3. Persist the policy identifier and inputs that determined the validity window.
4. Reuse the stored policy snapshot when Booking validates bookability.

#### Lifecycle and state expectations
- Quote validity must be immutable once the quote is issued; later policy
  catalog changes should not silently rewrite stored `validUntil` timestamps.
- Bookability checks should evaluate against the stored policy-derived validity
  window, not recompute from current rules.
- Repricing a quote may resolve a different validity policy if the new pricing
  mode or customer context differs from the original quote.

#### API implications
- Future quote responses should expose the matched validity policy identifier or
  policy class when support needs explainability beyond the raw timestamp.
- `GET /quotes/{id}/bookability` should expose whether the result was driven by
  normal expiry, customer-specific policy, or market-volatility constraints.
- Admin or reference-data APIs will likely need a managed validity-policy
  surface with draft, activation, and audit behavior comparable to other
  commercial rules.

#### Provenance and audit expectations
- Stored quote provenance should include the matched policy version and the
  inputs used to resolve it, such as pricing mode or contract reference.
- Changes to validity policies should be auditable because they directly affect
  quote promise windows seen by customers.
- Support should be able to reconstruct why two otherwise similar quotes
  received different validity windows.

#### Operational constraints
- Policy evaluation must remain fast because it sits on the hot path of quote
  creation and bookability checks.
- Policy configuration should guard against overlapping or contradictory rules
  that would produce non-deterministic validity outcomes.
- Monitoring should highlight lanes or customer segments where very short
  validity windows produce unusable quote churn.

#### Expected outcomes
- High-volatility quotes can expire sooner without changing stable tariff-based
  quote behavior.
- Support can explain why one customer received a shorter or longer validity
  window than another.
- Bookability checks remain deterministic because they use stored validity
  policy data rather than recomputing from mutable current rules.
