Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Prefer account contract pricing over customer pricing
    Given both a customer contract and a narrower account contract match the same shipment
    When the account requests a quote with both customer and account identity
    Then the account contract takes precedence deterministically
    And the resulting quote can differ from the customer-level contract for the same shipment inputs
