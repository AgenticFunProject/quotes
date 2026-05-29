Feature: Customer quote portfolio

  Scenario: List stored quotes for a customer portfolio
    Given a customer has stored quotes across multiple schedules
    When support filters the portfolio for that customer
    Then only that customer's quotes are returned
    And the newest matching quote appears first
