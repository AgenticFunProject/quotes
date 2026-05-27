Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Reject missing or invalid protected-route bearer tokens
    Given a client calls a protected Quotes admin or approval route
    When the bearer token is missing, malformed, expired, signed with the wrong secret, or has the wrong issuer or audience
    Then Quotes rejects the request as unauthenticated
    And the response does not expose credential material or signing-secret details
