Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Persist quote lifecycle events in the outbox
    Given the service stores quote lifecycle state and outbox events together
    When a client creates a quote and the quote is later read after expiry
    Then the service persists `quote.created` and `quote.expired` events for the same quote
    And each event includes the quote identifiers, stored commercial snapshot, and pricing provenance
