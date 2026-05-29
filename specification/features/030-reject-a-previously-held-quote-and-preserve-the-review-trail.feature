Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Reject a previously held quote and preserve the review trail
    Given a quote is waiting in a pending approval state
    When an authorized approver with quotes:approve rejects it with a decision reason
    Then the quote becomes non-bookable without recalculating the commercial amount
    And the service preserves the full rejection trail with approver identity, timestamp, and decision note
    And support can still retrieve the held quote and its original approval reasons for audit purposes
