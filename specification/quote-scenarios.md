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
