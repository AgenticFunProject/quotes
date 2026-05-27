Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Create a quote on a seeded peak-season lane
    Given the service has the seeded schedule and reference pricing data
    When a client requests a quote for the Rotterdam to New York schedule
    Then the API returns the commercial quote response shape documented in v1
    And the response includes the seasonal and congestion surcharges for that lane
    And the response includes both the internal quote UUID and the public quote reference
