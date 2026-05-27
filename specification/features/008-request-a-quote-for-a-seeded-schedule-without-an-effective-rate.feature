Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Request a quote for a seeded schedule without an effective rate
    Given the service recognizes the schedule identifier
    And no seeded base freight row exists for that route and equipment
    When the client requests a quote with that schedule and equipment
    Then the API rejects the request with a commercial validation error
