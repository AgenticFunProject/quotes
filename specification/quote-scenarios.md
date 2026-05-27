# Quote Scenarios

`specification/features/quotes.feature` is the tracked Gherkin source of truth for the quote service scenario catalog. Business-readable scenario prose lives there; HTTP actions, assertions, tokens, fixtures, and profile-specific settings live in `specification/gherkin-bindings.yaml`. This document keeps the contract coverage matrix for reviewers, and tests verify that the matrix, feature scenarios, and binding entries stay in the same order.

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
| Accept Users-issued Quotes-audience platform tokens for protected operations | `planned.accept_users_issued_tokens` |
| Accept gateway-issued Quotes-audience platform tokens for protected operations | `planned.accept_gateway_issued_tokens` |
| Reject missing or invalid protected-route bearer tokens | `planned.reject_missing_or_invalid_tokens` |
| Reject valid tokens without the required Quotes scope | `planned.reject_tokens_without_required_scope` |
| Resolve role=admin compatibility before implementation | `planned.resolve_role_admin_compatibility` |
| Keep web-page bearer propagation inside the gateway boundary | `planned.keep_gateway_bearer_boundary` |
| Verify Azure platform auth settings before deployment sign-off | `planned.verify_azure_auth_settings` |
| Keep Booking on public quote validation and Equipments on diagnostics | `planned.keep_booking_and_equipments_boundaries` |
