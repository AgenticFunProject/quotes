Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Validate rate coverage before requesting a quote
    Given the service stores seeded public tariff coverage by trade lane and equipment type
    When a client validates route, departure date, and equipment selection before pricing
    Then the API explains whether the requested combination is commercially covered
    And the response identifies which equipment selections are uncovered when no effective rate exists
