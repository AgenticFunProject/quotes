Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Accept Users-issued Quotes-audience platform tokens for protected operations
    Given Users can issue HS256 platform tokens from the local password login flow
    And the token uses the configured Quotes issuer, `quotes-service` audience, and shared signing secret
    When an operator calls a protected Quotes route with the required Quotes scope
    Then Quotes accepts the request after validating signature, issuer, audience, and expiry
    And the token subject remains the durable actor fallback when `X-Actor` is omitted
