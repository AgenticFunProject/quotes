Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Approve a previously held quote without changing the reviewed commercial snapshot
    Given a quote is waiting in a pending approval state
    And the held quote has a stored commercial snapshot and explicit approval reasons
    When an authorized approver with quotes:approve approves it with actor identity recorded
    Then the quote becomes issuable and bookable using the same commercial snapshot that was reviewed
    And the approval action is persisted with approver identity and timestamp
    And downstream consumers can distinguish the approval event from normal quote creation in the outbox stream
