Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Create, update, and activate a managed surcharge-rule version
    Given the service stores an active surcharge rule for a quoteable lane
    When a commercial operator creates, updates, and activates a managed surcharge-rule draft
    Then later quote requests apply the activated surcharge-rule version instead of the superseded active version
    And the stored quote provenance records the selected `surchargeRuleVersion`
