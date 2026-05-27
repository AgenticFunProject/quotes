Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Record an audit trail for managed commercial changes
    Given a commercial operator creates, edits, and activates a managed rate-table version
    When support reviews commercial change events for that rate table with `quotes:admin`
    Then the API returns the recorded `CREATED`, `UPDATED`, and `ACTIVATED` events
    And each event includes the actor, managed version, and post-change snapshot
