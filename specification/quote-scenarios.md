# Quote Scenarios

This document is the human-readable source of truth for the executable quote
service scenarios covered in `tests/test_quotes_api.py` and the documented
integration or deployment boundary scenarios guarded by `tests/test_documentation.py`.
Every scenario must describe a concrete actor, request path or input, and
observable response status or payload.

## Contract Coverage Matrix

This matrix is the rebuild gate for the scenario catalog. Each scenario must
point at at least one automated check that exercises the service behavior or
guards the documented integration/deployment boundary.

| Scenario | Executable coverage |
|---|---|
| Create a quote on a seeded peak-season lane | `tests/test_quotes_api.py::test_scenario_peak_season_quote_returns_the_documented_commercial_payload` |
| Retrieve a stored quote | `tests/test_quotes_api.py::test_scenario_quote_lookup_accepts_uuid_and_quote_reference` |
| Validate whether a stored quote can still be booked | `tests/test_quotes_api.py::test_scenario_booking_can_validate_quote_bookability` |
| Validate rate coverage before requesting a quote | `tests/test_quotes_api.py::test_scenario_route_coverage_validation_distinguishes_quoteable_lanes` |
| Plan equipment availability with explicit substitution suggestions | `tests/test_quotes_api.py::test_scenario_equipment_availability_plan_reports_direct_stock`<br>`tests/test_quotes_api.py::test_scenario_equipment_availability_plan_suggests_substitutions_for_shortage` |
| Persist quote lifecycle events in the outbox | `tests/test_quotes_api.py::test_scenario_quote_lifecycle_events_are_written_to_the_outbox` |
| Revoke an issued quote and block booking reuse | `tests/test_quotes_api.py::test_quote_revocation_requires_admin_scope`<br>`tests/test_quotes_api.py::test_quote_revocation_voids_quote_and_publishes_outbox_event`<br>`tests/test_quotes_api.py::test_quote_revocation_rejects_pending_approval_quote` |
| Request a quote for a seeded schedule without an effective rate | `tests/test_quotes_api.py::test_scenario_known_schedule_without_rate_returns_a_commercial_validation_error` |
| Apply customer contract pricing with surcharge waivers | `tests/test_quotes_api.py::test_scenario_contract_pricing_uses_customer_context_and_deterministic_precedence` |
| Prefer account contract pricing over customer pricing | `tests/test_quotes_api.py::test_scenario_contract_pricing_uses_customer_context_and_deterministic_precedence` |
| Create, update, and activate a managed rate-table version | `tests/test_quotes_api.py::test_admin_rate_table_draft_can_be_updated_and_activated` |
| Create, update, and activate a managed surcharge-rule version | `tests/test_quotes_api.py::test_admin_surcharge_rule_draft_can_be_updated_and_activated` |
| Require platform bearer authorization for commercial admin changes | `tests/test_quotes_api.py::test_admin_requires_platform_bearer_token_for_managed_commercial_changes`<br>`tests/test_quotes_api.py::test_admin_read_routes_require_platform_bearer_token` |
| Require platform bearer authorization for quote approval decisions | `tests/test_quotes_api.py::test_quote_approval_decision_requires_platform_bearer_token`<br>`tests/test_quotes_api.py::test_quote_approval_decision_rejects_token_without_approval_scope` |
| Check Equipments service connectivity | `tests/test_quotes_api.py::test_admin_equipments_connection_reports_successful_health_response`<br>`tests/test_quotes_api.py::test_admin_equipments_connection_reports_failed_health_response` |
| Record an audit trail for managed commercial changes | `tests/test_quotes_api.py::test_admin_rate_table_changes_are_recorded_in_audit_trail` |
| Publish managed commercial changes to the outbox | `tests/test_quotes_api.py::test_admin_rate_table_changes_are_published_to_outbox` |
| Replay outbox events for a named downstream consumer | `tests/test_quotes_api.py::test_admin_outbox_replay_advances_named_consumer_checkpoint` |
| Analyze quote impact for schedule or contract changes | `tests/test_quotes_api.py::test_admin_impact_analysis_persists_schedule_and_contract_results` |
| Preview quote pricing with draft managed commercial data | `tests/test_quotes_api.py::test_admin_quote_preview_can_use_draft_rate_and_surcharge_versions` |
| Return a quote in a requested display currency | `tests/test_quotes_api.py::test_scenario_requested_currency_quotes_include_fx_provenance` |
| Use approved market pricing when the client hints MARKET | `tests/test_quotes_api.py::test_create_quote_market_hint_uses_approved_market_rate_and_persists_trace` |
| Fall back from MARKET to contract or tariff pricing when market coverage is missing | `tests/test_quotes_api.py::test_create_quote_market_hint_falls_back_to_contract_when_market_is_unavailable` |
| Explain why a quote used market or fallback pricing | `tests/test_quotes_api.py::test_create_quote_market_hint_uses_approved_market_rate_and_persists_trace` |
| Reprice an existing quote and explain the commercial variance | `tests/test_quotes_api.py::test_reprice_existing_quote_preserves_original_and_reports_structured_variance`<br>`tests/test_quotes_api.py::test_reprice_quote_requires_admin_scope` |
| Return multiple commercial options for one quote request | `tests/test_quotes_api.py::test_create_quote_can_return_ordered_alternative_pricing_options` |
| Bound alternative options on quote creation | `tests/test_quotes_api.py::test_create_quote_can_limit_ordered_alternative_pricing_options`<br>`tests/test_quotes_api.py::test_create_quote_rejects_invalid_max_alternative_options` |
| Hold a quote for manual approval when commercial guardrails are exceeded | `tests/test_quotes_api.py::test_create_quote_holds_market_quote_for_approval_when_market_risk_guardrails_are_exceeded` |
| Approve a previously held quote without changing the reviewed commercial snapshot | `tests/test_quotes_api.py::test_quote_approval_decision_approves_pending_quote_without_repricing` |
| Reject a previously held quote and preserve the review trail | `tests/test_quotes_api.py::test_quote_approval_decision_can_reject_pending_quote` |
| Derive quote validity from a customer-specific policy | `tests/test_quotes_api.py::test_scenario_derive_quote_validity_from_customer_specific_policy` |
| Derive shorter quote validity from high-volatility market pricing | `tests/test_quotes_api.py::test_market_pricing_can_use_a_shorter_high_volatility_validity_policy` |
| Explain why similar quotes received different validity windows | `tests/test_quotes_api.py::test_scenario_derive_quote_validity_from_customer_specific_policy`<br>`tests/test_quotes_api.py::test_market_pricing_can_use_a_shorter_high_volatility_validity_policy` |
| Accept Users-issued Quotes-audience platform tokens for protected operations | `tests/test_documentation.py::test_quotes_spec_contains_2026_05_19_auth_rbac_deployment_plan` |
| Accept gateway-issued Quotes-audience platform tokens for protected operations | `tests/test_documentation.py::test_quotes_spec_contains_2026_05_19_auth_rbac_deployment_plan` |
| Reject missing or invalid protected-route bearer tokens | `tests/test_quotes_api.py::test_admin_requires_platform_bearer_token_for_managed_commercial_changes`<br>`tests/test_quotes_api.py::test_admin_rejects_invalid_protected_route_bearer_tokens` |
| Reject valid tokens without the required Quotes scope | `tests/test_quotes_api.py::test_admin_rejects_token_without_admin_scope`<br>`tests/test_quotes_api.py::test_quote_approval_decision_rejects_token_without_approval_scope` |
| Resolve role=admin compatibility before implementation | `tests/test_documentation.py::test_quotes_spec_contains_2026_05_19_auth_rbac_deployment_plan` |
| Keep web-page bearer propagation inside the gateway boundary | `tests/test_documentation.py::test_quotes_spec_contains_2026_05_19_auth_rbac_deployment_plan` |
| Verify Azure platform auth settings before deployment sign-off | `tests/test_azure_auth_deployment.py::test_azure_workflows_supply_platform_auth_from_github_secret_material` |
| Keep Booking on public quote validation and Equipments on diagnostics | `tests/test_documentation.py::test_quote_scenarios_cover_2026_05_19_auth_rbac_deployment_boundaries` |

## Scenario: Create a quote on a seeded peak-season lane

Given the service has the seeded schedule and reference pricing data
When a client posts to `POST /quotes` for the Rotterdam to New York schedule
Then the API returns the commercial quote response shape documented in v1
And the response includes the seasonal and congestion surcharges for that lane
And the response includes both the internal quote UUID and the public quote reference

## Scenario: Retrieve a stored quote

Given a quote has been stored by the service
When the client calls `GET /quotes/{id}` by internal UUID or public quote reference
Then the API returns the full stored quote record
And the stored quote includes the pricing basis and provenance snapshot used to create it
And the explicit `/quotes/reference/{quoteReference}` path returns the same payload as the primary lookup path

## Scenario: Validate whether a stored quote can still be booked

Given a quote has been stored by the service
When Booking calls `GET /quotes/{id}/bookability` for the quote UUID or quote reference
Then the API explains whether the quote is still usable from its validity
window
And the bookability check accepts the same quote UUID or quote reference used by quote lookup

## Scenario: Validate rate coverage before requesting a quote

Given the service stores seeded public tariff coverage by trade lane and equipment type
When a client validates route, departure date, and equipment selection before pricing
Then the API explains whether the requested combination is commercially covered
And the response identifies which equipment selections are uncovered when no effective rate exists

## Scenario: Plan equipment availability with explicit substitution suggestions

Given Booking rejects unavailable equipment during booking creation
And Equipments publishes availability counts by equipment type and depot
When a client posts to `POST /quotes/equipment-availability/plan` with requested equipment, an Equipments-style availability snapshot, and explicit substitution policy rows
Then the API reports whether the requested equipment is directly available, available through substitutions, or still short
And the API returns ordered substitution suggestions only from the supplied policy rows
And the API accepts the Equipments high-cube code `40HC` while returning the Quotes canonical code `40FT_HC`
And the API does not reserve equipment or create a quote

## Scenario: Persist quote lifecycle events in the outbox

Given the service stores quote lifecycle state and outbox events together
When a client posts to `POST /quotes` and the quote is later read after expiry
Then the service persists `quote.created` and `quote.expired` events for the same quote
And each event includes the quote identifiers, stored commercial snapshot, and pricing provenance

## Scenario: Revoke an issued quote and block booking reuse

Given an issued or approved quote is still unexpired and not booked
And a commercial operator has a platform bearer token with `quotes:admin`
When the operator posts to `POST /quotes/{id}/revocations` with a short reason
Then the quote lifecycle becomes `VOID`
And `GET /quotes/{id}/bookability` returns `bookable=false` with `status=VOID` and `reason=QUOTE_REVOKED`
And the service persists a `quote.revoked` outbox event with the actor, reason, commercial snapshot, and pricing provenance

## Scenario: Request a quote for a seeded schedule without an effective rate

Given the service recognizes the schedule identifier
And no seeded base freight row exists for that route and equipment
When the client posts to `POST /quotes` with that schedule and equipment
Then the API rejects the request with a commercial validation error

## Scenario: Apply customer contract pricing with surcharge waivers

Given the service stores seeded customer contract rules for the Rotterdam to New York lane
When a client posts to `POST /quotes` with `customerId` for that lane
Then the API prices the shipment from the matched contract instead of the public tariff
And the stored quote records the matched contract basis and waived surcharge types

## Scenario: Prefer account contract pricing over customer pricing

Given both a customer contract and a narrower account contract match the same shipment
When a client posts to `POST /quotes` with both `customerId` and `accountId`
Then the account contract takes precedence deterministically
And the resulting quote can differ from the customer-level contract for the same shipment inputs

## Scenario: Create, update, and activate a managed rate-table version

Given the service stores an active public tariff for a quoteable lane
When a commercial operator calls `POST /admin/rate-tables`, `PATCH /admin/rate-tables/{id}`, and `POST /admin/rate-tables/{id}/activate`
Then later quote requests use the activated rate-table version instead of the superseded active version
And the stored quote provenance records the selected `rateVersion`

## Scenario: Create, update, and activate a managed surcharge-rule version

Given the service stores an active surcharge rule for a quoteable lane
When a commercial operator calls `POST /admin/surcharge-rules`, `PATCH /admin/surcharge-rules/{id}`, and `POST /admin/surcharge-rules/{id}/activate`
Then later quote requests apply the activated surcharge-rule version instead of the superseded active version
And the stored quote provenance records the selected `surchargeRuleVersion`

## Scenario: Require platform bearer authorization for commercial admin changes

Given the service exposes internal `/admin/*` routes and quote repricing
When a client attempts to call an admin read, admin write, admin replay, diagnostic, quote preview, impact-analysis, or reprice route without a bearer token
Then the API rejects the request with `401`
And when the bearer token is valid but lacks `quotes:admin`
Then the API rejects the request with `403`
And when the bearer token has `quotes:admin`
Then the API accepts the change and records `X-Actor` as audit metadata when present

## Scenario: Require platform bearer authorization for quote approval decisions

Given a quote is waiting in a pending approval state
When a client attempts to approve or reject it without a bearer token
Then the API rejects the request with `401`
And when the bearer token is valid but lacks `quotes:approve`
Then the API rejects the request with `403`
And when the bearer token has `quotes:approve`
Then the API records the approval decision using `X-Actor` or the token subject as the approver identity

## Scenario: Check Equipments service connectivity

Given `EQUIPMENTS_SERVICE_URL` points at the Equipments service
And an operator has a platform bearer token with `quotes:admin`
When the operator calls `GET /admin/service-connections/equipments`
Then Quotes calls the configured Equipments `/health` endpoint
And the response reports `status` as `ok` when Equipments returns a healthy 2xx response
And the response reports `status` as `unhealthy` when the configured health call fails
And the response reports `status` as `not_configured` when `EQUIPMENTS_SERVICE_URL` is not configured
And the API never accepts a caller-supplied target URL for this diagnostic check

## Scenario: Record an audit trail for managed commercial changes

Given a commercial operator creates, edits, and activates a managed rate-table version
When support calls `GET /admin/commercial-change-events` for that rate table with `quotes:admin`
Then the API returns the recorded `CREATED`, `UPDATED`, and `ACTIVATED` events
And each event includes the actor, managed version, and post-change snapshot

## Scenario: Publish managed commercial changes to the outbox

Given a commercial operator creates, edits, and activates a managed rate-table version
When an integration consumer calls `GET /admin/outbox-events` for rate-table changes with `quotes:admin`
Then the service returns stable `rate.updated` events for each managed change
And each payload includes the commercial action, actor, resource version, and post-change snapshot

## Scenario: Replay outbox events for a named downstream consumer

Given the service stores quote lifecycle and managed commercial events in the outbox
When a downstream consumer with `quotes:admin` replays events with its named checkpoint
Then the API returns the next ordered batch of matching events
And the consumer checkpoint advances so the next replay can resume without rereading old events

## Scenario: Analyze quote impact for schedule or contract changes

Given the service stores quotes with schedule and contract provenance
When an operator with `quotes:admin` posts to `POST /admin/impact-analyses` for a schedule or contract change
Then the service persists a summary of the affected quotes
And the summary reports each affected quote's identifiers, lifecycle state, and current bookability

## Scenario: Preview quote pricing with draft managed commercial data

Given the service stores active public tariff data and draft replacement commercial rows
When a commercial operator posts to `POST /admin/quote-preview` with explicit draft rate-table and surcharge-rule identifiers
Then the API prices the shipment without persisting a quote
And the response provenance records the draft managed versions that would be used after activation

## Scenario: Return a quote in a requested display currency

Given the service stores governed FX data for supported quote currencies
When a client posts to `POST /quotes` with `currency` set to `EUR`
Then the API keeps the commercial source basis in `USD`
And the response exposes the persisted FX snapshot and rounding policy used for conversion
And the stored quote provenance records both the source total and the display-currency total deterministically

## Scenario: Use approved market pricing when the client hints MARKET

Given the service stores approved market-rate snapshots for the requested lane and equipment
When a client posts to `POST /quotes` with `pricingModeHint` set to `MARKET`
Then the API prices the base freight from the approved market snapshot instead of tariff or contract data
And the stored quote records the selected market source and optimization trace for explainability

## Scenario: Fall back from MARKET to contract or tariff pricing when market coverage is missing

Given the service cannot fully cover the request from approved market-rate snapshots
When a client posts to `POST /quotes` with `pricingModeHint` set to `MARKET`
Then the API falls back to the deterministic contract-or-tariff basis available for that request
And the stored optimization trace records that market pricing was requested but unavailable

## Scenario: Explain why a quote used market or fallback pricing

Given a quote has been stored with market-pricing explainability data
When support reads `GET /quotes/{id}/explain`
Then the API returns the stored pricing basis, market source when present, and persisted optimization trace
And the explainability payload matches the stored pricing provenance used at quote creation time

## Scenario: Reprice an existing quote and explain the commercial variance

Given a quote has been stored from an earlier commercial snapshot
And the stored quote records its original pricing basis, FX snapshot, and optimization trace
And newer approved commercial data is now active for the same shipment request
When an operator with `quotes:admin` requests a reprice for the same shipment inputs
Then the service preserves the original quote unchanged and stores a distinct repriced result
And the repriced quote keeps a durable link back to the original quote identifier and quote reference
And the repriced response reports the structured variance across base rate, surcharges, FX, and optimization inputs
And the response classifies the overall variance direction as higher, lower, or unchanged
And support can later read both the original and repriced provenance snapshots without recomputing current rules

## Scenario: Return multiple commercial options for one quote request

Given more than one eligible pricing basis can satisfy the same shipment request
And the client requests alternative commercial options
When a client posts to `POST /quotes` with alternative options enabled and a bounded option count
Then the API returns a primary priced option and an ordered set of alternative quote options
And each option includes its own bookable commercial provenance snapshot
And alternatives are ordered deterministically by total source amount and pricing-basis precedence

## Scenario: Bound alternative options on quote creation

Given the service has multiple eligible pricing bases for a quote request
When a client posts to `/quotes` with `includeAlternativeOptions=true` and `maxAlternativeOptions=1`
Then the response keeps the selected primary option
And the response returns only the best ordered alternative option
And `maxAlternativeOptions` values below 1 or above 10 are rejected as request validation errors
And `maxAlternativeOptions` without `includeAlternativeOptions=true` does not add an `options` object

## Scenario: Hold a quote for manual approval when commercial guardrails are exceeded

Given a market-priced quote violates a configured market-risk approval guardrail
When the client posts to `POST /quotes` for that shipment
Then the service stores the quote in a pending approval state instead of issuing it directly
And the stored quote records the exact approval reasons that must be reviewed
And the quote is not bookable while it remains pending approval
And the quote-created outbox event captures the pending lifecycle state and approval reasons

## Scenario: Approve a previously held quote without changing the reviewed commercial snapshot

Given a quote is waiting in a pending approval state
And the held quote has a stored commercial snapshot and explicit approval reasons
When an authorized approver with `quotes:approve` approves it with actor identity recorded
Then the quote becomes issuable and bookable using the same commercial snapshot that was reviewed
And the approval action is persisted with approver identity and timestamp
And downstream consumers can distinguish the approval event from normal quote creation in the outbox stream

## Scenario: Reject a previously held quote and preserve the review trail

Given a quote is waiting in a pending approval state
When an authorized approver with `quotes:approve` rejects it with a decision reason
Then the quote becomes non-bookable without recalculating the commercial amount
And the service preserves the full rejection trail with approver identity, timestamp, and decision note
And support can still retrieve the held quote and its original approval reasons for audit purposes

## Scenario: Derive quote validity from a customer-specific policy

Given the service stores multiple quote validity policies by customer, contract, or pricing mode
And the matching policy resolves from the customer's contract or pricing mode instead of the default validity rule
When a client posts to `POST /quotes` with inputs that match a non-default validity policy
Then the API derives `validUntil` from the matched policy instead of the generic default window
And the stored quote records the policy provenance used by later bookability checks
And later bookability validation uses the stored policy-derived validity window even if the current policy catalog has changed

## Scenario: Derive shorter quote validity from high-volatility market pricing

Given the service stores an approved market-rate snapshot with high-volatility signals
When a client posts to `POST /quotes` with `pricingModeHint` set to `MARKET` for that lane
Then the API derives `validUntil` from the high-volatility validity policy
And the stored quote provenance records the matched validity policy and market-signal inputs
And later `GET /quotes/{id}/bookability` evaluates the stored high-volatility validity window

## Scenario: Explain why similar quotes received different validity windows

Given one stored quote matched an account validity policy
And another stored quote matched the high-volatility market validity policy
When support reads `GET /quotes/{id}` or `GET /quotes/{id}/explain` for each quote
Then each payload exposes the stored `pricingProvenance.validityPolicy` snapshot
And support can compare the policy identifier, matched inputs, and resulting `validUntil` values without recomputing current policy rules

## Scenario: Accept Users-issued Quotes-audience platform tokens for protected operations

Given Users can issue HS256 platform tokens from the local password login flow
And the token uses the configured Quotes issuer, `quotes-service` audience, and shared signing secret
When an operator calls a protected Quotes route with the required Quotes scope
Then Quotes accepts the request after validating signature, issuer, audience, and expiry
And the token subject remains the durable actor fallback when `X-Actor` is omitted

## Scenario: Accept gateway-issued Quotes-audience platform tokens for protected operations

Given the web-page gateway exposes `/api/auth/quotes-token` for local operator demos
When the gateway-issued token has `aud` set to `quotes-service` and the required Quotes scope
Then protected Quotes routes can accept it as a local demo token
And the documentation labels this as a developer helper rather than production identity-provider behavior

## Scenario: Reject missing or invalid protected-route bearer tokens

Given a client calls a protected Quotes admin or approval route
When the bearer token is missing, malformed, expired, signed with the wrong secret, or has the wrong issuer or audience
Then Quotes returns `401`
And the response does not expose credential material or signing-secret details

## Scenario: Reject valid tokens without the required Quotes scope

Given a client has a valid platform token for the Quotes audience
When the token lacks `quotes:admin` for admin operations or `quotes:approve` for approval decisions
Then Quotes returns `403`
And the route does not perform the protected operation

## Scenario: Resolve role=admin compatibility before implementation

Given Equipments accepts a validated `role=admin` token for privileged operations
And Quotes currently documents scope-based authorization
When the platform decides whether Quotes should accept `role=admin`
Then the decision is recorded before runtime auth code changes
And tests cover the selected behavior without allowing role claims to bypass issuer, audience, expiry, or signature checks

## Scenario: Keep web-page bearer propagation inside the gateway boundary

Given public quote creation and lookup stay unauthenticated
When the web-page calls `/api/quotes` for customer quote workflows
Then the browser helper does not attach bearer tokens to those public requests
And any future protected Quotes UI operation attaches Quotes-audience tokens only to the explicit protected path

## Scenario: Verify Azure platform auth settings before deployment sign-off

Given Quotes is deployed through the Azure workflow
When maintainers sign off a deployment that includes protected route behavior
Then `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE=quotes-service`, and `AUTH_JWT_SECRET` are configured from non-local secret material
And verification covers public quote behavior, a protected `quotes:admin` route, a protected `quotes:approve` route, and rejection of an Equipments-audience token

## Scenario: Keep Booking on public quote validation and Equipments on diagnostics

Given Booking consumes quote validity and pricing provenance
And Equipments remains a separate protected inventory service
When the current integration boundary is implemented
Then Booking uses public quote validation and lookup routes without forwarding caller bearer tokens
And Quotes only calls Equipments through the configured admin connectivity diagnostic until a new service contract is accepted
