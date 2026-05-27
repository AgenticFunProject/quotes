Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Bound alternative options on quote creation
    Given the service has multiple eligible pricing bases for a quote request
    When a client requests one bounded alternative option for the quote
    Then the response keeps the selected primary option
    And the response returns only the best ordered alternative option
    And `maxAlternativeOptions` values below 1 or above 10 are rejected as request validation errors
    And `maxAlternativeOptions` without `includeAlternativeOptions=true` does not add an `options` object
