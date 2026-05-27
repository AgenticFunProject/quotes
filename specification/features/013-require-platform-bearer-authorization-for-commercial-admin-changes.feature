Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Require platform bearer authorization for commercial admin changes
    Given the service exposes protected commercial admin routes and quote repricing
    When a client attempts to call an admin read, admin write, admin replay, diagnostic, quote preview, impact-analysis, or reprice route without a bearer token
    Then the API rejects the request as unauthenticated
    And when the bearer token is valid but lacks `quotes:admin`
    Then the API rejects the request as unauthorized
    And when the bearer token has `quotes:admin`
    Then the API accepts the change and records `X-Actor` as audit metadata when present
