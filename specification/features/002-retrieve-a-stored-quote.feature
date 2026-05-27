Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Retrieve a stored quote
    Given a quote has been stored by the service
    When the client looks up the quote by internal UUID or public quote reference
    Then the API returns the full stored quote record
    And the stored quote includes the pricing basis and provenance snapshot used to create it
    And the dedicated quote-reference lookup returns the same payload as the primary lookup
