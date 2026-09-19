## Why

A Blender MCP client can already run arbitrary Python inside the user's session,
but nothing in the add-on is meant to be called that way: a simulation has five
entry points (two scene toggles, two debug operators, the manager methods) with
hidden preconditions, silent no-ops, results that exist only as Blender shape-key
data, and no way to tell a finished run from a refused one. The user has had to
hand-write that sequence in a notebook to test anything, and an agent cannot
reproduce it.

## What Changes

- Add `qyapi`, a script-facing module of the add-on, reachable under that name in
  any session where the add-on is registered (viewport open or `-b`), usable
  without an operator, a modal context or a menu, returning only JSON-safe data.
- Add discovery for a client that cannot read the repository: `qyapi.help()` and
  `qyapi.state()`.
- Address everything by name (project, pattern); a call MUST NOT require a uuid
  or a Blender object carried over from an earlier call.
- Redesign simulation control as one call per intent: `sim.prepare()`,
  `sim.step(frames)`, `sim.start()`, `sim.stop()`, `sim.status()`, `sim.read()`
  and `sim.reset()`.
- Make synchronous stepping the agent path: it advances the engine on the calling
  thread for exactly the requested number of substeps and returns metrics. The
  timer-driven free run stays available for a human watching, and the two modes
  exclude each other instead of one silently doing nothing.
- Make every refusal explicit: an intersecting outline, an unprepared session, a
  live run in progress and an engine failure each report what happened.
- Give write calls an undo granularity: one named undo step per call, plus a
  transaction that collapses a multi-call intent into one step.
- Document the surface twice: in the module itself, so a client that can only run
  Python can still find it, and in a shipped reference file. Both MUST state the
  units, the coordinate spaces, the addressing scheme and the calls to avoid.
- Document the add-on's own data model in the same two places: which objects
  exist, how they nest, how each one is reached from a session and which call is
  the supported way to change it. Reaching into Blender objects and their data
  directly is permitted but discouraged, so the documentation also states the
  refresh step such a write needs and the failures that follow from skipping it.

Not in this change: an MCP server or MCP tool definitions; the panel authoring
and editing facade; any engine or DP backend change; any new UI.

## Capabilities

### New Capabilities

- `agent-scripting-surface`: the importable module, its discovery calls,
  name-based addressing, JSON-safe return values, the error contract, undo
  granularity and the documented data model that covers what the entry points do
  not.
- `agent-simulation-control`: preparing, stepping, running, stopping, reading and
  resetting a simulation from a script, and the state those calls report.

### Modified Capabilities

None. This repository has no capability in `openspec/specs/` yet, so no existing
requirement changes.

## Impact

- New code: one module in the add-on, the registration that publishes it, its
  documentation, and the reference file that mirrors that documentation.
- `Qianyi/simulation/simulation_manager.py`: the stepping path stops swallowing
  engine exceptions and reports them; the live free-run path keeps its behaviour.
- Unchanged: the engine contract, the sewing and mesh data models, every existing
  operator and panel, and the `.blend` format. No persisted state is added.
- No new dependency: numpy, as bundled with Blender.
