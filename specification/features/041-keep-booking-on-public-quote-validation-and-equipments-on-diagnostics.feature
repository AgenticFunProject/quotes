Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Keep Booking on public quote validation and Equipments on diagnostics
    Given Booking consumes quote validity and pricing provenance
    And Equipments remains a separate protected inventory service
    When the current integration boundary is implemented
    Then Booking uses public quote validation and lookup routes without forwarding caller bearer tokens
    And Quotes only calls Equipments through the configured admin connectivity diagnostic until a new service contract is accepted
