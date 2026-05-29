Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Explain why similar quotes received different validity windows
    Given one stored quote matched an account validity policy
    And another stored quote matched the high-volatility market validity policy
    When support reviews the stored quote and pricing explanation for each quote
    Then each explanation exposes the stored validity policy snapshot
    And support can compare the policy identifier, matched inputs, and resulting validity windows without recomputing current policy rules
