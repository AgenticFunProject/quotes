Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Return a quote in a requested display currency
    Given the service stores governed FX data for supported quote currencies
    When a client requests a quote in a euro display currency
    Then the quote keeps the commercial source basis in United States dollars
    And the response exposes the persisted FX snapshot and rounding policy used for conversion
    And the stored quote provenance records both the source total and the display-currency total deterministically
