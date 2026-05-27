Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Reprice an existing quote and explain the commercial variance
    Given a quote has been stored from an earlier commercial snapshot
    And the stored quote records its original pricing basis, FX snapshot, and optimization trace
    And newer approved commercial data is now active for the same shipment request
    When an operator with `quotes:admin` requests a reprice for the same shipment inputs
    Then the service preserves the original quote unchanged and stores a distinct repriced result
    And the repriced quote keeps a durable link back to the original quote identifier and quote reference
    And the repriced response reports the structured variance across base rate, surcharges, FX, and optimization inputs
    And the response classifies the overall variance direction as higher, lower, or unchanged
    And support can later read both the original and repriced provenance snapshots without recomputing current rules
