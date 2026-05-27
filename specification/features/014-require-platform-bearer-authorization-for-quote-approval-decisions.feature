Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Require platform bearer authorization for quote approval decisions
    Given a quote is waiting in a pending approval state
    When a client attempts to approve or reject it without a bearer token
    Then the API rejects the request as unauthenticated
    And when the bearer token is valid but lacks `quotes:approve`
    Then the API rejects the request as unauthorized
    And when the bearer token has `quotes:approve`
    Then the API records the approval decision using `X-Actor` or the token subject as the approver identity
