Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Return multiple commercial options for one quote request
    Given more than one eligible pricing basis can satisfy the same shipment request
    And the client requests alternative commercial options
    When a client requests a quote with alternative options enabled and a bounded option count
    Then the API returns a primary priced option and an ordered set of alternative quote options
    And each option includes its own bookable commercial provenance snapshot
    And alternatives are ordered deterministically by total source amount and pricing-basis precedence
