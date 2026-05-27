Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Fall back from MARKET to contract or tariff pricing when market coverage is missing
    Given the service cannot fully cover the request from approved market-rate snapshots
    When a client requests a quote with `pricingModeHint` set to `MARKET`
    Then the API falls back to the deterministic contract-or-tariff basis available for that request
    And the stored optimization trace records that market pricing was requested but unavailable
