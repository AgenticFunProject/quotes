Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Verify Azure platform auth settings before deployment sign-off
    Given Quotes is deployed through the Azure workflow
    When maintainers sign off a deployment that includes protected route behavior
    Then `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE=quotes-service`, and `AUTH_JWT_SECRET` are configured from non-local secret material
    And verification covers public quote behavior, a protected `quotes:admin` route, a protected `quotes:approve` route, and rejection of an Equipments-audience token
