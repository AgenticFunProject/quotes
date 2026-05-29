Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Explain why a quote used market or fallback pricing
    Given a quote has been stored with market-pricing explainability data
    When support reviews the quote's pricing explanation
    Then the explanation returns the stored pricing basis, market source when present, and persisted optimization trace
    And the explainability payload matches the stored pricing provenance used at quote creation time
