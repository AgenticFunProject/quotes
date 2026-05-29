Feature: Idempotent quote request replay

  Scenario: Replay a quote request with an idempotency key
    Given a customer has prepared a quote request with a stable replay key
    When the same request is submitted twice with that replay key
    Then the customer receives the original quote reference on the replay
    And the quote ledger records only one created quote event for that key
