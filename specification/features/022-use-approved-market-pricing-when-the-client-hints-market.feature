Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Use approved market pricing when the client hints MARKET
    Given the service stores approved market-rate snapshots for the requested lane and equipment
    When a client requests a quote with `pricingModeHint` set to `MARKET`
    Then the API prices the base freight from the approved market snapshot instead of tariff or contract data
    And the stored quote records the selected market source and optimization trace for explainability
