Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Publish managed commercial changes to the outbox
    Given a commercial operator creates, edits, and activates a managed rate-table version
    When an integration consumer reads rate-table outbox events with `quotes:admin`
    Then the service returns stable `rate.updated` events for each managed change
    And each payload includes the commercial action, actor, resource version, and post-change snapshot
