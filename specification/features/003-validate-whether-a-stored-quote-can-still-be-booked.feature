Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Validate whether a stored quote can still be booked
    Given a quote has been stored by the service
    When Booking validates the stored quote by UUID or quote reference
    Then the API explains whether the quote is still usable from its validity window
    And the bookability check accepts the same quote UUID or quote reference used by quote lookup
