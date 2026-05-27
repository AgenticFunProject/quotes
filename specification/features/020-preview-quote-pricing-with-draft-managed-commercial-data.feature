Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Preview quote pricing with draft managed commercial data
    Given the service stores active public tariff data and draft replacement commercial rows
    When a commercial operator previews pricing with explicit draft rate-table and surcharge-rule identifiers
    Then the API prices the shipment without persisting a quote
    And the response provenance records the draft managed versions that would be used after activation
