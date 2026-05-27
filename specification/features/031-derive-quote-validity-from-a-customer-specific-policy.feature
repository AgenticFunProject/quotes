Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Derive quote validity from a customer-specific policy
    Given the service stores multiple quote validity policies by customer, contract, or pricing mode
    And the matching policy resolves from the customer's contract or pricing mode instead of the default validity rule
    When a client requests a quote with inputs that match a non-default validity policy
    Then the API derives `validUntil` from the matched policy instead of the generic default window
    And the stored quote records the policy provenance used by later bookability checks
    And later bookability validation uses the stored policy-derived validity window even if the current policy catalog has changed
