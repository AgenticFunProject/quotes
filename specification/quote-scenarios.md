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

## Scenario: Use approved market pricing when the client hints MARKET

Given the service stores approved market-rate snapshots for the requested lane and equipment
When a client requests a quote with `pricingModeHint` set to `MARKET`
Then the API prices the base freight from the approved market snapshot instead of tariff or contract data
And the stored quote records the selected market source and optimization trace for explainability

## Scenario: Fall back from MARKET to contract or tariff pricing when market coverage is missing

Given the service cannot fully cover the request from approved market-rate snapshots
When a client requests a quote with `pricingModeHint` set to `MARKET`
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
When an operator requests a reprice for the same shipment inputs
Then the service preserves the original quote unchanged and stores a distinct repriced result
And the repriced quote keeps a durable link back to the original quote identifier and quote reference
And the repriced response reports the structured variance across base rate, surcharges, FX, and optimization inputs
And the response classifies the overall variance direction as higher, lower, or unchanged
And support can later read both the original and repriced provenance snapshots without recomputing current rules

## Scenario: Return multiple commercial options for one quote request

Given more than one eligible service option can satisfy the same shipment request
And the service has a configured ranking policy for primary and alternative options
When a client requests a quote with alternative options enabled and a bounded option count
Then the API returns a primary priced option and an ordered set of alternative quote options
And each option includes its own bookable commercial provenance snapshot
And each option exposes stable ranking metadata so the client can explain why it is primary, cheapest, fastest, or otherwise preferred
And the response includes a stable option identifier that Booking can use to select one option later without repricing the full request

## Scenario: Hold a quote for manual approval when commercial guardrails are exceeded

Given a priced quote violates an approval guardrail such as margin or waiver policy
When the client requests the quote
Then the service stores the quote in a pending approval state instead of issuing it directly
And the stored quote records the exact approval reasons that must be reviewed
And the quote is not bookable while it remains pending approval
And a durable audit record captures the breached guardrail inputs and policy version that caused the hold

## Scenario: Approve a previously held quote without changing the reviewed commercial snapshot

Given a quote is waiting in a pending approval state
And the held quote has a stored commercial snapshot and explicit approval reasons
When an authorized approver approves it with actor identity recorded
Then the quote becomes issuable and bookable using the same commercial snapshot that was reviewed
And the approval action is persisted with approver identity and timestamp
And downstream consumers can distinguish the approval event from normal quote creation in the outbox stream

## Scenario: Reject a previously held quote and preserve the review trail

Given a quote is waiting in a pending approval state
When an authorized approver rejects it with a decision reason
Then the quote becomes non-bookable without recalculating the commercial amount
And the service preserves the full rejection trail with approver identity, timestamp, and decision note
And support can still retrieve the held quote and its original approval reasons for audit purposes

## Scenario: Derive quote validity from a customer-specific policy

Given the service stores multiple quote validity policies by customer, contract, or pricing mode
And the matching policy resolves from the customer's contract or pricing mode instead of the default validity rule
When a client requests a quote that matches a non-default validity policy
Then the API derives `validUntil` from the matched policy instead of the generic default window
And the stored quote records the policy provenance used by later bookability checks
And later bookability validation uses the stored policy-derived validity window even if the current policy catalog has changed

## Scenario: Explain why similar quotes received different validity windows

Given two otherwise similar quote requests match different validity policies
When support compares the stored quotes after creation
Then the service can explain which policy version each quote matched
And support can see which customer, contract, pricing-mode, or volatility inputs produced the different `validUntil` timestamps

## Scenario: Document the current repository landscape explicitly

Given the Quotes service now operates inside a larger multi-repository town workspace
When a maintainer reads `specification/system-architecture.md`
Then the document distinguishes the Quotes git worktree from the surrounding rig and town paths
And the document lists the currently confirmed repositories separately from visible but not fully documented system components

## Scenario: Mark unsupported architecture detail as assumptions or gaps

Given not every visible town component has a maintained contract in this repository
When the architecture-state document describes control-plane components outside the Quotes repo
Then unverified responsibilities are labeled as assumptions or gaps instead of settled facts
And the document records which service integrations are explicitly confirmed today

## Scenario: Keep the service specification linked to the broader architecture state

Given `specification/quotes.md` is the main service contract for Quotes behavior
When a reader reviews the current integration boundaries in that specification
Then the reader is directed to `specification/system-architecture.md` for repository-level system state
And the service specification keeps its own boundary focused on quote runtime dependencies and consumers
