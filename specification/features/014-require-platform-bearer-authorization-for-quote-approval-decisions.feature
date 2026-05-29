Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Require platform bearer authorization for quote approval decisions
    Given a quote is waiting in a pending approval state
    When an approval decision arrives without platform bearer authorization
    Then the service rejects the decision as unauthenticated
    And when the bearer token lacks the quotes:approve permission
    Then the service rejects the decision as unauthorized
    And when the bearer token includes the quotes:approve permission
    Then the service records the approval decision with the approver identity
