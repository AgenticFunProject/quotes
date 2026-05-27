Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Check Equipments service connectivity
    Given `EQUIPMENTS_SERVICE_URL` points at the Equipments service
    And an operator has a platform bearer token with `quotes:admin`
    When the operator checks the Equipments service connection
    Then Quotes calls the configured Equipments health check
    And the response reports `status` as `ok` when Equipments reports healthy service availability
    And the response reports `status` as `unhealthy` when the configured health call fails
    And the response reports `status` as `not_configured` when `EQUIPMENTS_SERVICE_URL` is not configured
    And the API never accepts a caller-supplied target URL for this diagnostic check
