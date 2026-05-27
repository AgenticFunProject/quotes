Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Accept gateway-issued Quotes-audience platform tokens for protected operations
    Given the web-page gateway exposes a local operator token helper
    When the gateway-issued token has `aud` set to `quotes-service` and the required Quotes scope
    Then protected Quotes routes can accept it as a local demo token
    And the documentation labels this as a developer helper rather than production identity-provider behavior
