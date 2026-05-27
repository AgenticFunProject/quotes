Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Derive shorter quote validity from high-volatility market pricing
    Given the service stores an approved market-rate snapshot with high-volatility signals
    When a client requests market pricing for that lane
    Then the API derives `validUntil` from the high-volatility validity policy
    And the stored quote provenance records the matched validity policy and market-signal inputs
    And later bookability validation evaluates the stored high-volatility validity window
