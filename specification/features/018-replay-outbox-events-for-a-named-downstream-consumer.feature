Feature: Quote service contract scenarios
  Quotes exposes public quote workflows, protected operator workflows,
  and documented integration boundaries as business-readable contracts.

  Scenario: Replay outbox events for a named downstream consumer
    Given the service stores quote lifecycle and managed commercial events in the outbox
    When a downstream consumer with `quotes:admin` replays events with its named checkpoint
    Then the API returns the next ordered batch of matching events
    And the consumer checkpoint advances so the next replay can resume without rereading old events
