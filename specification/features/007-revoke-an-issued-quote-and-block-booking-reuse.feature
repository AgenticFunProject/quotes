Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Revoke an issued quote and block booking reuse
    Given an issued or approved quote is still unexpired and not booked
    And a commercial operator has a platform bearer token with `quotes:admin`
    When the operator revokes the quote with a short reason
    Then the quote lifecycle becomes `VOID`
    And a later bookability check reports that the quote is not bookable because it was revoked
    And the service persists a `quote.revoked` outbox event with the actor, reason, commercial snapshot, and pricing provenance
