Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Keep web-page bearer propagation inside the gateway boundary
    Given public quote creation and lookup stay unauthenticated
    When the web-page calls the gateway quote helper for customer quote workflows
    Then the browser helper does not attach bearer tokens to those public requests
    And any future protected Quotes UI operation attaches Quotes-audience tokens only to the explicit protected path
