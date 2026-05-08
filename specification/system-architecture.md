# System Architecture State

## Purpose

This document records the current system-level repository and workspace state around the Quotes service.

It complements `specification/quotes.md`, which defines the service contract, by documenting the broader repository landscape, control-plane boundaries, integration assumptions, and known gaps that exist today.

## Maintenance Rules

- Treat this document as a maintained snapshot of confirmed architecture state, not a speculative target design.
- Prefer evidence visible in the current workspace, repository contents, and committed documentation.
- Mark anything not directly confirmed here as an assumption or gap.
- Update this document whenever a repository is added, removed, renamed, or given a new responsibility that changes system boundaries.

## State Legend

- Confirmed: directly supported by the current workspace, repository contents, or committed documentation.
- Assumption: likely true from naming or surrounding context, but not fully specified in this repository.
- Gap: an integration or ownership boundary that is visible but not yet documented well enough.

## Current Workspace Topology

Confirmed paths visible from the current workspace:

- Town root: `/home/user/gt`
- Quotes rig root: `/home/user/gt/quotes`
- Quotes git worktree used for implementation: `/home/user/gt/quotes/polecats/obsidian/quotes`

That distinction matters:

- The Quotes git repository is not the same thing as the Quotes rig root.
- The rig root contains runtime and orchestration directories in addition to the service repository.
- Service code and service documentation changes belong in the Quotes git worktree, while rig runtime state lives outside that worktree.

## Confirmed Repository Landscape

The following git repositories are directly confirmed from the current town workspace.

| Repository | Evidence | Current role | State |
|------------|----------|--------------|-------|
| `quotes` | Current worktree remote is `AgenticFunProject/quotes`; contains `app/`, `tests/`, `specification/`, `.github/workflows/`, and `infra/azure/` | Business repository for the Quotes FastAPI service, its tests, deployment workflow, and product/specification docs | Confirmed |
| `mayor` | `/home/user/gt/mayor/.git` exists; issue dispatch metadata shows `dispatched_by: mayor`; town context names Mayor as global coordinator | Town-level coordination repository for dispatch and control-plane configuration | Confirmed for existence and coordination role |
| `deacon` | `/home/user/gt/deacon/.git` exists; repository contains `.beads/`, `dogs/`, `heartbeat.json`, `feed-stranded-state.json`, and `state.json` | Operational or supervisory repository tied to runtime state and watchdog-style bookkeeping | Confirmed for existence, assumption for exact responsibility |

## Visible Non-Repository System Components

The following paths are visible at the town root but were not confirmed here as independently versioned git repositories.

| Path | Observed state | Current interpretation | State |
|------|----------------|------------------------|-------|
| `/home/user/gt/gastown` | Contains `.beads/` and `mayor/` | Shared system or town-control assets | Assumption |
| `/home/user/gt/beads` | Contains `.beads/` | Issue-tracking data or support assets for the Beads toolchain | Assumption |
| `/home/user/gt/witness` | Visible at town root | Monitoring or health-supervision component referenced by worker instructions | Assumption |
| `/home/user/gt/events` | Visible at town root | Shared event or runtime support area | Gap |
| `/home/user/gt/daemon` | Visible at town root | Shared long-running system process area | Gap |
| `/home/user/gt/plugins` | Visible at town root | Shared plugin or extension area | Gap |
| `/home/user/gt/logs` | Visible at town root | Shared runtime logs | Confirmed |
| `/home/user/gt/backups` | Visible at town root | Shared backup storage | Confirmed |

## Quotes Repository Responsibilities

Within the current repository, the confirmed responsibilities are:

- expose the Quotes HTTP API through FastAPI
- calculate and persist quotes against local seeded or managed commercial data
- persist quote lifecycle and commercial outbox records
- carry the current product specification, scenarios, and architecture notes
- run local and CI verification through `tests/`, `scripts/verify.sh`, and GitHub Actions
- define Azure deployment assets through `infra/azure/` and workflow automation

This repository is the system's documented business boundary. It does not currently document or implement the whole town control plane.

## Quotes Service Runtime Boundary

The current Quotes runtime remains intentionally narrow.

Confirmed service-level dependencies from this repository's specification and README:

- `Schedules API` is the only explicitly named upstream service dependency, and is currently represented in implementation by a local `ScheduleProvider` abstraction backed by an in-memory stub.
- Booking is a downstream consumer of stored quotes and quote lifecycle state, not a live dependency required to calculate a quote.
- The frontend is expected to consume the Quotes HTTP API directly; no separate frontend repository is confirmed from this workspace.
- Quote lifecycle and managed commercial changes are persisted through an outbox-first design, with broker adoption explicitly deferred.

Implication:

- quote calculation should continue to work even if town-level control repositories are unavailable, as long as the service process and its local data are available
- town-level repositories orchestrate work and system operations, but they are not part of the quote-pricing request path described in `specification/quotes.md`

## Control Plane Versus Business Plane

The current system is best understood as two adjacent planes.

### Business plane

- `quotes` repository
- FastAPI application code under `app/`
- SQLite-backed local persistence
- product and API specification under `specification/`
- tests and CI workflows

### Control plane

- town and rig orchestration rooted at `/home/user/gt`
- bead-driven work dispatch and tracking
- mayor, witness, refinery, and polecat operating model referenced by agent instructions
- runtime state, logs, and heartbeat-style coordination outside the Quotes git worktree

This boundary is important because it prevents service documentation from drifting into unsupported claims about orchestration internals while still acknowledging that the Quotes repository operates inside a larger multi-repository system.

## Known Gaps And Explicit Assumptions

### Confirmed gaps

- No maintained document in this repository previously described the full town and rig repository state.
- No local Booking repository is confirmed from the current workspace.
- No local Schedules repository is confirmed from the current workspace.
- No local frontend repository is confirmed from the current workspace.
- The exact responsibility split among `deacon`, `gastown`, `events`, `daemon`, and `plugins` is not documented from within this repository.

### Explicit assumptions

- `mayor` acts as the central dispatcher and coordination authority for work because assignments are dispatched by Mayor and town context names that role directly.
- `deacon` participates in health, supervision, or recovery flows because its repository contains heartbeat and stranded-state files, but the formal contract is not documented here.
- `witness` remains an operational observer or supervisor because worker instructions reference it repeatedly, but its repository and interfaces were not inspected here.

## Expected Evolution

Near-term architecture evolution already implied by the Quotes specifications:

1. Replace the in-memory schedules stub with a real schedules integration behind the existing provider boundary.
2. Keep Booking as a downstream consumer of stored quote state, with tighter documented contracts as Booking integration becomes concrete.
3. Continue with the outbox-first eventing model until at least two meaningful downstream consumers justify broker adoption.
4. Expand this document when currently assumed town components gain stable repository contracts or clearer ownership.

## Documentation Contract

When this document is updated, keep these invariants true:

- `specification/quotes.md` remains the service contract for business behavior.
- this document remains the broader repository and boundary map for the current system state.
- every non-confirmed statement is labeled as an assumption or gap rather than presented as settled architecture.
