Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Apply customer contract pricing with surcharge waivers
    Given the service stores seeded customer contract rules for the Rotterdam to New York lane
    When a client requests a quote with customer context for that lane
    Then the API prices the shipment from the matched contract instead of the public tariff
    And the stored quote records the matched contract basis and waived surcharge types
