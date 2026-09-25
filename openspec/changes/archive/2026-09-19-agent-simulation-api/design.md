## Context

See proposal.md for motivation and the specs for the behaviour contract. What
shapes the approach:

- A simulation has five entry points today and no single one of them expresses
  "run this scene and tell me what happened": the scene toggles
  (`enable_free_simulation`, `simulation_with_animation` in
  `Qianyi/model/simulation_data.py`), two debug operators
  (`qmyi.simulation_debug_next_n_frames`, `qmyi.simulation_debug_to_n_frames` in
  `Qianyi/ui/panels_3d/simulation.py`), the manager methods
  (`SimulationManager.start_simulation` / `stop_simulation`), and the raw engine
  path the study notebook uses (`qydp.simulator.set_parameters` / `input_data` /
  `update` / `get_simulation_data`).
- The order a caller has to reproduce is: `refresh_all_uuids` -> outline
  validation -> pattern parameters -> `setup_data` (which rebuilds sewings and
  regenerates meshes) -> engine `input_data` -> per-substep update -> apply the
  result. Each entry point performs a different subset.
- `SimulationManager._update_one_frame` calls `self.simulator.update(...)` inside
  a bare `try/except` that sets `running = False` and discards the exception, and
  `update_N_frames_debug` returns immediately when `self.running` is true. A
  caller cannot tell a finished run from a refused one, and `self.simulator` is
  only bound by the task thread's `_run`, so a stepping call made before any run
  silently does nothing.
- The live run is a task on `TaskManager`'s background Python thread (a 1 ms
  scheduled task); the results are applied to the meshes on the main thread by a
  `bpy.app.timers` callback. Two drivers - a background task and a script - can
  therefore interleave.
- Simulated positions live in the per-object `QYSim` shape key and are readable
  only through Blender data; there is no position read-back call and no metric.
- Undo, measured in this repository on Blender 4.5.6 in a `-b` session:
  `bpy.ops.ed.undo_push(message=...)` returns `{'FINISHED'}`, while
  `bpy.ops.ed.undo()` raises `RuntimeError: Operator bpy.ops.ed.undo.poll()
  failed, context is incorrect`. `undo_pre` clears `global_data.uuid2obj`, and
  `after_undo_redo` refreshes the project only when a node editor is active.
- A Blender MCP client runs one short Python statement per tool call in the live
  session and holds no state between calls. The add-on package name depends on
  how it was loaded (`qmyi` in the study-notebook loader, `Qianyi` when
  installed), so an agent cannot be asked to guess an import path.
- No third-party dependency: numpy as bundled with Blender.

## Goals / Non-Goals

**Goals:**

- One call per intent, with the internal ordering owned by the add-on.
- A substep count that depends on the arguments and not on wall-clock time.
- One place to read the session state, and modes that cannot silently overlap.
- Failures that reach the caller with the substep they happened on.
- Undo granularity: one visible step per intent, none for simulation results.

**Non-Goals:**

- Any engine or DP backend change: the mesh payload, the sewing list and the
  `update`/`get_simulation_data` contract stay as they are.
- Pattern authoring and editing entry points; this change adds the surface they
  will later live in, not the tools themselves.
- An MCP server, MCP tool definitions or a protocol layer of any kind.
- New UI. The existing panels keep their behaviour.
- Bitwise reproducible results: PDNewton is not bitwise deterministic run to run
  (a known, separately tracked issue in the engine repository), so only the
  substep arithmetic is specified here.

## Decisions

### D1 - A module named `qyapi`, published under that name

The surface is a Python package inside the add-on, and registration publishes it
as `qyapi` in `sys.modules`, so `import qyapi` works in every session where the
add-on is registered. The documented fallback is importing it from the add-on
package for a session that has not registered the add-on yet.

*Alternatives*: an operator namespace such as `bpy.ops.qyapi.*` (rejected: an
operator needs a context, cannot return structured data, and would add an undo
step or a menu to every call); a submodule import only (rejected: the package
name varies with how the add-on was loaded, so the agent would have to guess);
a new MCP server (rejected: the client already runs Python, and the user asked
for documentation of an existing client rather than a second integration).

### D2 - One session state machine

The simulation surface owns a single state with the modes `idle`, `prepared`,
`stepping`, `live` and `failed`. Every entry point reads it first, the mutual
exclusions in the specs are state rules rather than scattered conditions, and
`status()` reports exactly this state.

*Alternatives*: drive the existing `SimulationManager.running` flag from the
script path (rejected: the flag is written from the task thread, and reusing it
is what makes today's entry points silently no-op); a command queue with a
worker thread (rejected: an agent call already runs on the main thread between
Blender events, so a second thread would add scheduling without removing any
coupling).

### D3 - Stepping runs on the calling thread; the live run keeps the task

`step()` advances the engine in the caller's own call and applies the results
before returning. The live run keeps `TaskManager` plus the `bpy.app.timers`
application callback, so a human watching the viewport is unaffected.

*Alternatives*: start the live run and poll it (rejected: a blocking call stops
Blender's timers, so the run would not advance while the caller waits, and the
result would depend on machine load); a new engine-side stepping API (rejected:
the engine contract is owned by another workstream and does not need to change
to satisfy this).

### D4 - The stepping path reports engine errors instead of discarding them

The step call drives the engine through a wrapper that lets the exception reach
the caller, and the session leaves the stepping mode on the way out. The live
path keeps the existing catch-and-stop behaviour, because it has no caller to
report to. The surface deliberately adds no progress reporting: the engine
reports no per-substep state, and a substep index produced by the surface's own
loop would describe the loop, not the simulation.

*Alternatives*: change `_update_one_frame` for both paths (rejected: it changes
the user-visible live run for no gain and makes the change touch a path it does
not need); report the failing substep and the completed count (rejected: it is
detail the caller cannot act on, and the user asked for the error alone).

### D5 - Undo granularity: one push per intent, after the mutations

A public write call ends with a single `bpy.ops.ed.undo_push`, labelled with the
caller's intent. A transaction collapses nested writes into one step. Read calls
never push. A session that cannot undo (no window) applies the change and treats
the push as a no-op.

The rule that follows from Blender's semantics: `undo_push` records the current
state, so the push goes *after* the mutations, and a transaction MUST NOT call an
operator that carries the `UNDO` option (`{'REGISTER', 'UNDO'}` on every editing
operator in this add-on), because that would push a step in the middle of the
batch and split it.

*Alternatives*: push before the batch (rejected: it leaves an extra empty step
and a history entry that says nothing); never push (rejected: an agent's edits
would be invisible in the undo history, which is the only place a user can see
what the agent did); wrap each internal mutation in its own step (rejected: a
single intent would cost the user several undos).

### D6 - Address by name; resolve at the start of every call

Every entry point resolves names through the identity map after refreshing it, so
undo, redo and file loading cannot leave a call holding a stale identity.

*Alternatives*: uuid (rejected: the wrapper moves when an element is deleted,
which is the `obj.global_uuid != uuid` crash, and the map is cleared by undo);
collection index (rejected: it shifts on delete); handing Blender objects back
to the caller (rejected: they are invalid after undo and cannot cross a tool
call boundary).

### D7 - Return plain data only

Results are dictionaries and lists of primitives; numpy arrays are converted
before they are returned. The client stringifies results, and a Blender object
in a result is unusable to it.

### D8 - Solver parameters are an explicit input to preparation

`prepare()` takes the solver name and parameter block, applies them itself and
records in its summary that the caller supplied them. The scene panel is used
only when the caller does not pass parameters.

*Alternatives*: keep the panel authoritative through `apply_on_start` (rejected:
a value a human left in the pattern would silently override the agent's
parameters, which is exactly the class of silent behaviour this change removes).

### D9 - Metrics are measured or passed through, never invented

Wall time and substep and frame counts are produced by the surface. Engine
statistics appear unchanged when the engine exposes them and are absent when it
does not, so a missing residual or timing number cannot be mistaken for a zero.

### D10 - The UI keeps working through the same entry points

The scene toggles delegate to the same start and stop calls the surface exposes,
so `status()` cannot report a mode the running code is not in.

### D11 - The data model is documented, and direct Blender access is permitted but discouraged

The surface cannot cover every corner on the first pass, and a client that finds
a gap will reach for Blender data anyway. The documentation therefore describes
the object model explicitly - the project, its patterns, vertices, edges, spline
points, internal lines, sewings, fabrics and the simulation mesh objects - says
how each is reached, names the supported call for each change, and states plainly
that reaching into Blender data directly is allowed but discouraged, together
with the refresh step and the failure that follows from skipping it.

*Alternatives*: document only the entry points (rejected: a gap then turns into an
invented access path, and in this add-on that ends in a crash rather than an
error); forbid direct access (rejected: it cannot be enforced from Python, and a
prohibition a client cannot obey is worse than a documented hazard); describe the
data model only in the repository file (rejected: a client that can only run
Python would not see it, which is why the text index is readable by topic).

## Risks / Trade-offs

- A long `step()` call holds Blender's main thread and freezes the viewport ->
  document a per-call substep budget, return after the requested substeps, and
  let the caller split a long run into several calls.
- Stepping writes the simulated shape key, which is not undoable, while earlier
  edits are -> document that a run is not an edit and that `reset()` is the way
  back; the undo requirement in the spec keeps the history free of run noise.
- The engine stays a process-wide singleton, so two Blender sessions cannot share
  it -> out of scope here; the surface at least makes a second session's
  attempt visible instead of silent.
- Two drivers can still meet if the user flips the toggle during a scripted run
  -> the mode rule refuses the second one and names the active mode.
- A blocking script cannot repaint, so a human watching a scripted run sees a
  frozen viewport until the call returns -> documented; the live mode is the
  answer for watching.
- The engine's own per-substep statistics are not available today -> the specs
  require them to be absent rather than fabricated, and the engine can add them
  later without a surface change.
- A client that bypasses the surface can still crash the session -> the
  documented data model names the refresh step and the specific failures (a
  stale identity after an undo, a moved wrapper after a delete, a hand-written
  shape key), so the discouraged path has a known cost rather than an unknown
  one.

## Migration Plan

- Additive: a new package, its registration and its documentation. Every
  existing entry point keeps working during and after the change.
- Nothing persisted changes, so an older `.blend` opens unchanged and a file
  saved by this version opens in an older add-on.
- Rollback: remove the package and its registration line; the only edit to
  shared code is the error-reporting wrapper on the stepping path.

## Open Questions

- Whether the shipped reference file belongs under `docs/` or next to the
  module; both satisfy the discovery requirement and the choice can be made
  while writing the documentation.
- Whether reading back positions should also expose per-stitch sewing positions;
  deferrable, because the pattern positions are what a first agent workflow needs.
