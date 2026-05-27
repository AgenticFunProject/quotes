Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Resolve role=admin compatibility before implementation
    Given Equipments accepts a validated `role=admin` token for privileged operations
    And Quotes currently documents scope-based authorization
    When the platform decides whether Quotes should accept `role=admin`
    Then the decision is recorded before runtime auth code changes
    And tests cover the selected behavior without allowing role claims to bypass issuer, audience, expiry, or signature checks
