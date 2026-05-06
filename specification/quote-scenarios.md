# Quote Scenarios

This document is the human-readable source of truth for the executable quote
service scenarios covered in `tests/test_quotes_api.py`.

## Scenario: Create a quote on a seeded peak-season lane

Given the service has the seeded schedule and reference pricing data
When a client requests a quote for the Rotterdam to New York schedule
Then the API returns the commercial quote response shape documented in v1
And the response includes the seasonal and congestion surcharges for that lane
And the response includes both the internal quote UUID and the public quote reference

## Scenario: Retrieve a stored quote

Given a quote has been stored by the service
When the client looks it up by internal UUID or public quote reference
Then the API returns the full stored quote record
And the stored quote includes the pricing basis and provenance snapshot used to create it
And the explicit `/quotes/reference/{quoteReference}` path returns the same payload as the primary lookup path

## Scenario: Validate whether a stored quote can still be booked

Given a quote has been stored by the service
When Booking asks for the quote's bookability status
Then the API explains whether the quote is still usable from its validity
window
And the bookability check accepts the same quote UUID or quote reference used by quote lookup

## Scenario: Validate rate coverage before requesting a quote

Given the service stores seeded public tariff coverage by trade lane and equipment type
When a client validates route, departure date, and equipment selection before pricing
Then the API explains whether the requested combination is commercially covered
And the response identifies which equipment selections are uncovered when no effective rate exists

## Scenario: Persist quote lifecycle events in the outbox

Given the service stores quote lifecycle state and outbox events together
When a client creates a quote and that quote later expires
Then the service persists `quote.created` and `quote.expired` events for the same quote
And each event includes the quote identifiers, stored commercial snapshot, and pricing provenance

## Scenario: Request a quote for a seeded schedule without an effective rate

Given the service recognizes the schedule identifier
And no seeded base freight row exists for that route and equipment
When the client requests a quote
Then the API rejects the request with a commercial validation error

## Scenario: Apply customer contract pricing with surcharge waivers

Given the service stores seeded customer contract rules for the Rotterdam to New York lane
When a client requests a quote with `customerId` for that lane
Then the API prices the shipment from the matched contract instead of the public tariff
And the stored quote records the matched contract basis and waived surcharge types

## Scenario: Prefer account contract pricing over customer pricing

Given both a customer contract and a narrower account contract match the same shipment
When a client requests a quote with both `customerId` and `accountId`
Then the account contract takes precedence deterministically
And the resulting quote can differ from the customer-level contract for the same shipment inputs

## Scenario: Create, update, and activate a managed rate-table version

Given the service stores an active public tariff for a quoteable lane
When a commercial operator creates a draft replacement rate table, updates it, and activates it
Then later quote requests use the activated rate-table version instead of the superseded active version
And the stored quote provenance records the selected `rateVersion`

## Scenario: Create, update, and activate a managed surcharge-rule version

Given the service stores an active surcharge rule for a quoteable lane
When a commercial operator creates a draft replacement surcharge rule, updates it, and activates it
Then later quote requests apply the activated surcharge-rule version instead of the superseded active version
And the stored quote provenance records the selected `surchargeRuleVersion`

## Scenario: Require actor identity for commercial admin changes

Given the service exposes internal managed-commercial-data admin endpoints
When a client attempts to create a managed rate or surcharge change without `X-Actor`
Then the API rejects the request because the audit actor is required

## Scenario: Record an audit trail for managed commercial changes

Given a commercial operator creates, edits, and activates a managed rate-table version
When support reads the managed commercial audit trail for that rate table
Then the API returns the recorded `CREATED`, `UPDATED`, and `ACTIVATED` events
And each event includes the actor, managed version, and post-change snapshot

## Scenario: Publish managed commercial changes to the outbox

Given a commercial operator creates, edits, and activates a managed rate-table version
When an integration consumer reads the outbox feed for rate-table changes
Then the service returns stable `rate.updated` events for each managed change
And each payload includes the commercial action, actor, resource version, and post-change snapshot

## Scenario: Replay outbox events for a named downstream consumer

Given the service stores quote lifecycle and managed commercial events in the outbox
When a downstream consumer replays events with its named checkpoint
Then the API returns the next ordered batch of matching events
And the consumer checkpoint advances so the next replay can resume without rereading old events

## Scenario: Analyze quote impact for schedule or contract changes

Given the service stores quotes with schedule and contract provenance
When an operator creates an impact analysis for a schedule or contract change
Then the service persists a summary of the affected quotes
And the summary reports each affected quote's identifiers, lifecycle state, and current bookability

## Scenario: Preview quote pricing with draft managed commercial data

Given the service stores active public tariff data and draft replacement commercial rows
When a commercial operator previews a quote with explicit draft rate-table and surcharge-rule identifiers
Then the API prices the shipment without persisting a quote
And the response provenance records the draft managed versions that would be used after activation

## Scenario: Return a quote in a requested display currency

Given the service stores governed FX data for supported quote currencies
When a client requests a quote with `currency` set to `EUR`
Then the API keeps the commercial source basis in `USD`
And the response exposes the persisted FX snapshot and rounding policy used for conversion
And the stored quote provenance records both the source total and the display-currency total deterministically
