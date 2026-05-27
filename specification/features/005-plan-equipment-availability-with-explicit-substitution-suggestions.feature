Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Plan equipment availability with explicit substitution suggestions
    Given Booking rejects unavailable equipment during booking creation
    And Equipments publishes availability counts by equipment type and depot
    When a client asks Quotes to plan requested equipment with an Equipments-style availability snapshot and explicit substitution policy rows
    Then the API reports whether the requested equipment is directly available, available through substitutions, or still short
    And the API returns ordered substitution suggestions only from the supplied policy rows
    And the API accepts the Equipments high-cube code `40HC` while returning the Quotes canonical code `40FT_HC`
    And the API does not reserve equipment or create a quote
