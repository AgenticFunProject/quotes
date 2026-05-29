Feature: Quote lifecycle timeline

  Scenario: Read a quote lifecycle timeline
    Given an issued quote has durable lifecycle activity
    When customer service opens the quote timeline
    Then the timeline shows the current quote state
    And the lifecycle events are returned in business order
