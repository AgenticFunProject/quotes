# ADR 001: Eventing Strategy For Quotes

## Status

Accepted

## Context

The current quotes service is a single FastAPI application backed by SQLite. It exposes synchronous HTTP endpoints for quote creation and retrieval, uses a local schedule stub, and has no asynchronous consumers yet.

The roadmap includes future consumers and workflows that will benefit from quote lifecycle events:

- Booking validating and consuming quotes
- audit and commercial reporting
- notification or workflow automation
- future pricing analytics and optimization inputs

The immediate design question is whether the service should introduce Kafka now, choose another broker now, or defer broker adoption until the service has real asynchronous integration pressure.

## Decision

Do not introduce Kafka in the current phase.

Adopt an outbox-first eventing design now, and add a message broker later when the service has multiple independent consumers or operational requirements that justify it.

## Why

- The service currently has one synchronous API surface and no proven need for high-throughput streaming.
- Kafka would add significant operational complexity relative to the present scope: broker management, topic design, producer semantics, local development overhead, and failure handling.
- The repository already targets Azure deployment, where a simpler managed queue or bus is a more natural next step than self-managed Kafka if asynchronous fan-out becomes necessary.
- An outbox table gives the service a durable event contract today without forcing an immediate broker decision.

## Decision Details

### Now

Implement quote lifecycle events inside the service boundary:

- create an `outbox_events` table
- write quote state changes and matching outbox rows in the same transaction
- define versioned event payloads such as `quote.created`, `quote.expired`, and `quote.consumed`
- run a lightweight dispatcher that can publish events to logs, webhooks, or a future broker adapter

This keeps quote creation synchronous and reliable while making downstream publishing retriable.

### Later

Introduce a broker when one or more of these conditions become true:

- Booking and at least one other service both need quote events independently
- consumers need replay beyond what direct HTTP callbacks can support
- the service needs back-pressure isolation between quote writes and downstream processing
- event volume or fan-out makes polling the outbox directly impractical

## Broker Guidance

If a broker is needed in the near-to-medium term, prefer a managed bus that fits the deployment environment and operational maturity of the project.

Pragmatic order of choice:

1. Azure Service Bus or a similarly managed queue/topic service if the need is reliable fan-out, retries, and workflow decoupling.
2. Kafka only when the platform needs durable replay, multiple consumer groups, high event throughput, or stream-processing style use cases.

Kafka is not rejected permanently. It is deferred until the architecture actually needs Kafka-specific strengths.

## Consequences

### Positive

- Lower complexity now while preserving a clean migration path later.
- Durable event records are available immediately for audit and retry.
- The synchronous HTTP API stays simple for clients.
- Broker choice remains open until real consumers and scale requirements are known.

### Negative

- An outbox dispatcher is still additional implementation work.
- Some latency-sensitive use cases may eventually outgrow polling or lightweight dispatch.
- A future broker rollout will still require operational work and consumer onboarding.

## Implementation Notes

- Event payloads should include both internal IDs and public quote references.
- Events should carry enough snapshot data to avoid forcing consumers to rehydrate mutable upstream context.
- Store event type, version, payload, occurred timestamp, publish status, and retry metadata.
- Keep broker-specific code behind a publisher interface so the first managed bus or Kafka integration does not leak into quote domain logic.

## Resulting Architecture Direction

The quotes service remains request/response at its core.

Eventing becomes a durable side effect of quote lifecycle changes, starting with an internal outbox and evolving to a broker only when downstream consumers justify that operational step.
