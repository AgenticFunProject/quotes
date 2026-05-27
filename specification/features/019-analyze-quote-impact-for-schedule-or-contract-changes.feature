Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Analyze quote impact for schedule or contract changes
    Given the service stores quotes with schedule and contract provenance
    When an operator with `quotes:admin` requests impact analysis for a schedule or contract change
    Then the service persists a summary of the affected quotes
    And the summary reports each affected quote's identifiers, lifecycle state, and current bookability
