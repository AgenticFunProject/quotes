# Quote Scenarios

`specification/features/` is the tracked Gherkin source of truth for the quote service scenario catalog. Each `.feature` file contains one business-readable scenario, and the numeric filename prefix preserves the deterministic contract order from `specification/gherkin-bindings.yaml`. HTTP actions, assertions, tokens, fixtures, and profile-specific settings live in `specification/gherkin-bindings.yaml`. This document keeps the contract coverage matrix and route-level coverage audit for reviewers.

## Feature File Convention

- Use one tracked `.feature` file per scenario.
- Name files as `<ordinal>-<scenario-slug>.feature`, where `<ordinal>` is the one-based order in `specification/gherkin-bindings.yaml`.
- Keep exactly one `Feature:` heading and exactly one `Scenario:` or `Scenario Outline:` block in each file.
- Preserve scenario names and order between the feature files and `specification/gherkin-bindings.yaml`.

The contract runner loads the directory in filename order, validates the one-scenario-per-file convention, and compares the resulting scenario list to the binding map.

## Coverage Audit

Audit date: 2026-05-27.

Audit inputs:

- `app/main.py` route decorators
- `specification/quotes.md`
- `README.md#current-api-surface`
- `specification/gherkin-bindings.yaml`
- `tests/test_quotes_api.py`
- `tests/test_gherkin_contract_runner.py`

The current 44-scenario catalog covers the business contract surface documented for Quotes. `GET /health` is intentionally excluded from the Gherkin catalog because it is a generic readiness probe covered by `tests/test_health.py`, not a quote business workflow.

| Product surface | Contract coverage |
|---|---|
| Public quote creation, quote read by ID/reference, bookability, revocation, and lifecycle outbox behavior | `Create a quote on a seeded peak-season lane`; `Retrieve a stored quote`; `Validate whether a stored quote can still be booked`; `Revoke an issued quote and block booking reuse`; `Persist quote lifecycle events in the outbox` |
| Customer operations for replay safety, quote portfolio history, and lifecycle audit views | `Replay a quote request with an idempotency key`; `List stored quotes for a customer portfolio`; `Read a quote lifecycle timeline` |
| Rate coverage and equipment availability planning | `Validate rate coverage before requesting a quote`; `Plan equipment availability with explicit substitution suggestions`; `Request a quote for a seeded schedule without an effective rate` |
| Customer/account contract, market pricing, currency, repricing, pricing explainability, alternatives, validity, and manual approval workflows | Pricing and validity scenarios 9-33 in the matrix below |
| Protected-route platform bearer behavior, cross-repo token source decisions, gateway boundary, Azure auth settings, and downstream integration boundaries | Auth and integration-boundary scenarios 34-41 in the matrix below |
| Managed rate-table and surcharge-rule admin workflows | `Create, update, and activate a managed rate-table version`; `Create, update, and activate a managed surcharge-rule version`; `Record an audit trail for managed commercial changes`; `Publish managed commercial changes to the outbox` |
| Commercial diagnostics, outbox replay, impact analysis, and quote preview | `Check Equipments service connectivity`; `Replay outbox events for a named downstream consumer`; `Analyze quote impact for schedule or contract changes`; `Preview quote pricing with draft managed commercial data` |

## Contract Coverage Matrix

This matrix is the rebuild gate for the scenario catalog. Each scenario points
at exactly one binding entry. Executable bindings can be listed, validated,
dry-run, and run against configured service profiles.

| Scenario | Binding |
|---|---|
| Create a quote on a seeded peak-season lane | `smoke.create_peak_season_quote` |
| Retrieve a stored quote | `smoke.retrieve_stored_quote` |
| Validate whether a stored quote can still be booked | `smoke.validate_stored_quote_bookability` |
| Validate rate coverage before requesting a quote | `readiness.validate_rate_coverage_before_quote` |
| Plan equipment availability with explicit substitution suggestions | `readiness.plan_equipment_availability` |
| Persist quote lifecycle events in the outbox | `lifecycle.persist_quote_lifecycle_events` |
| Revoke an issued quote and block booking reuse | `smoke.revoke_quote_blocks_booking_reuse` |
| Request a quote for a seeded schedule without an effective rate | `readiness.request_quote_without_effective_rate` |
| Apply customer contract pricing with surcharge waivers | `planned.apply_customer_contract_pricing` |
| Prefer account contract pricing over customer pricing | `planned.prefer_account_contract_pricing` |
| Create, update, and activate a managed rate-table version | `admin.manage_rate_table_version` |
| Create, update, and activate a managed surcharge-rule version | `admin.manage_surcharge_rule_version` |
| Require platform bearer authorization for commercial admin changes | `auth.require_admin_authorization` |
| Require platform bearer authorization for quote approval decisions | `planned.require_approval_authorization` |
| Check Equipments service connectivity | `diagnostics.check_equipments_connectivity` |
| Record an audit trail for managed commercial changes | `admin.record_commercial_audit_trail` |
| Publish managed commercial changes to the outbox | `admin.publish_commercial_changes_to_outbox` |
| Replay outbox events for a named downstream consumer | `admin.replay_outbox_events` |
| Analyze quote impact for schedule or contract changes | `admin.analyze_quote_impact` |
| Preview quote pricing with draft managed commercial data | `admin.preview_quote_pricing` |
| Return a quote in a requested display currency | `planned.return_requested_display_currency` |
| Use approved market pricing when the client hints MARKET | `planned.use_approved_market_pricing` |
| Fall back from MARKET to contract or tariff pricing when market coverage is missing | `planned.fall_back_from_market_pricing` |
| Explain why a quote used market or fallback pricing | `planned.explain_pricing_basis` |
| Reprice an existing quote and explain the commercial variance | `pricing.reprice_existing_quote` |
| Return multiple commercial options for one quote request | `pricing.return_multiple_commercial_options` |
| Bound alternative options on quote creation | `pricing.bound_alternative_options` |
| Hold a quote for manual approval when commercial guardrails are exceeded | `planned.hold_quote_for_manual_approval` |
| Approve a previously held quote without changing the reviewed commercial snapshot | `planned.approve_held_quote` |
| Reject a previously held quote and preserve the review trail | `planned.reject_held_quote` |
| Derive quote validity from a customer-specific policy | `planned.derive_customer_specific_validity` |
| Derive shorter quote validity from high-volatility market pricing | `planned.derive_market_validity` |
| Explain why similar quotes received different validity windows | `planned.explain_validity_differences` |
| Accept Users-issued Quotes-audience platform tokens for protected operations | `auth.accept_users_issued_tokens` |
| Accept gateway-issued Quotes-audience platform tokens for protected operations | `auth.accept_gateway_issued_tokens` |
| Reject missing or invalid protected-route bearer tokens | `auth.reject_missing_or_invalid_tokens` |
| Reject valid tokens without the required Quotes scope | `auth.reject_tokens_without_required_scope` |
| Resolve role=admin compatibility before implementation | `auth.resolve_role_admin_compatibility` |
| Keep web-page bearer propagation inside the gateway boundary | `docs.keep_gateway_bearer_boundary` |
| Verify Azure platform auth settings before deployment sign-off | `deployment.verify_azure_auth_settings` |
| Keep Booking on public quote validation and Equipments on diagnostics | `docs.keep_booking_and_equipments_boundaries` |
| Replay a quote request with an idempotency key | `customer_operations.replay_quote_request_with_idempotency_key` |
| List stored quotes for a customer portfolio | `customer_operations.list_customer_quote_portfolio` |
| Read a quote lifecycle timeline | `customer_operations.read_quote_lifecycle_timeline` |
