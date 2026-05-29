Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Apply customer contract pricing with surcharge waivers
    Given a customer contract covers the Rotterdam to New York lane
    When a customer requests a quote for that contract lane
    Then the quote uses the matched customer contract instead of the public tariff
    And the pricing explanation records the customer contract and waived surcharge types
