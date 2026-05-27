Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Hold a quote for manual approval when commercial guardrails are exceeded
    Given a market-priced quote violates a configured market-risk approval guardrail
    When the client requests a quote for that shipment
    Then the service stores the quote in a pending approval state instead of issuing it directly
    And the stored quote records the exact approval reasons that must be reviewed
    And the quote is not bookable while it remains pending approval
    And the quote-created outbox event captures the pending lifecycle state and approval reasons
