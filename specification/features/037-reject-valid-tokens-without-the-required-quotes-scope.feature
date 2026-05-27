Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Reject valid tokens without the required Quotes scope
    Given a client has a valid platform token for the Quotes audience
    When the token lacks `quotes:admin` for admin operations or `quotes:approve` for approval decisions
    Then Quotes rejects the request as unauthorized
    And the route does not perform the protected operation
