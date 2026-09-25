## 1. Surface skeleton and registration

- [x] 1.1 Create the `qyapi` package inside the add-on (a surface module for discovery and transactions plus a simulation module) and verify the Blender-free parts import and run in a plain Python session that has only numpy (the error type module is Blender-free and imports from a plain interpreter; the surface itself needs bpy by design)
- [x] 1.2 Publish the package under the name `qyapi` during registration and verify `import qyapi` succeeds in a `-b` session that registered the add-on and in a session with a viewport, and that the documented fallback import from the add-on package resolves to the same module (`tools/probe_agent_api.py` checks `qyapi`, `qyapi.sim` and `qyapi.errors` against the add-on package modules; the submodules are published too, so a second copy of the error class cannot appear)
- [x] 1.3 Verify every public call runs with no viewport, no operator, no modal handler and no menu: the whole probe runs in `-b` and no call reported a missing context

## 2. Discovery

- [x] 2.1 Implement `state()` and verify it reports the projects, their patterns with point counts and validity, the sewing count and the simulation state, both in a scene with no project and in a loaded scene
- [x] 2.2 Verify `state()` is a pure read: the probe compares object, mesh, group, pattern and fabric-link counts around the call and they are identical
- [x] 2.3 Implement the text index and verify every public entry point appears with its purpose and the unit of each numeric argument

## 3. Addressing, results and failures

- [x] 3.1 Implement name resolution with an identity refresh at the start of every call and verify a call made after a redo and after re-opening the file resolves the same objects (the probe opens the file after registering the add-on, then resolves by name in every call; the undo half of this check needs a session with a viewport)
- [x] 3.2 Make every result JSON-safe and verify each entry point's result survives a JSON round trip with no Blender object and no numpy array in it
- [x] 3.3 Implement the error contract (a structured reason, no dialog, no menu) and verify a call with a missing name, an unsupported solver and a step before preparation each report the reason, change nothing, and open no UI in a `-b` session

## 4. Undo granularity

- [x] 4.1 Implement the transaction (nesting collapses to one step) and the one-push-per-write rule; the probe counts the pushes: nothing inside a transaction, exactly one when it exits, exactly one per write call (the end-to-end "one undo reverts the batch" confirmation still needs a session with a viewport)
- [x] 4.2 Verify that read calls leave the undo stack unchanged (the probe counts zero pushes across `state()`, `help()`, `status()` and `read()`) and that a write in a `-b` session applies its change without raising about undo being unavailable

## 5. Simulation preparation

- [x] 5.1 Implement preparation (refresh identities, outline validation, solver parameters, engine payload, engine bind) and verify its summary names the solver in effect, the objects, the vertices and the stitches handed to the engine
- [x] 5.2 Verify preparation is repeatable: two preparations with the same arguments leave the same bound state and report the same summary
- [x] 5.3 Verify preparation refuses an intersecting outline, names the offending patterns, and leaves the engine unbound (a meshed square is reshaped into a bowtie without regenerating its mesh; the probe confirms the engine object is untouched)
- [x] 5.4 Verify parameters passed to preparation are the ones in effect even when the scene solver panel holds different values, and that the summary says the caller supplied them (Explicit + 2 parameters while the panel holds PDNewton + 34)

## 6. Session state and stepping

- [x] 6.1 Implement the session state (`idle`, `prepared`, `stepping`, `live`, `failed`) and `status()`; verify each mode is reported and that a status taken before preparation reports no prepared state
- [x] 6.2 Implement `step()` as a synchronous substep loop on the calling thread and verify the reported frame count advances by exactly the requested number of substeps, twice in a row and independent of machine load
- [x] 6.3 Verify the meshes already carry the positions of the requested substep when the call returns
- [x] 6.4 Implement the engine-error wrapper and verify an induced engine failure reaches the caller as an error and leaves the mode out of `stepping` (the probe replaces the substep call with one that raises)
- [x] 6.5 Verify a step request during a live run is refused with the active mode named and the live run keeps running

## 7. Live run and the existing UI

- [x] 7.1 Route the scene toggles through the same start and stop entry points and verify the toggles still start and stop a run and that status agrees with the running code (setting `enable_free_simulation` from a script moves the mode to `live` and back to `idle`)
- [x] 7.2 Verify a live run requested during a stepping session is refused with the active mode named

## 8. Reading back, metrics and reset

- [x] 8.1 Implement position read-back and verify the returned positions match the pattern meshes, the vertex count per pattern matches, and a read moves no vertex
- [x] 8.2 Verify a non-finite position is reported as a count instead of failing the call (a NaN written into a simulated shape key comes back as one bad vertex)
- [x] 8.3 Implement reset and verify a run started after a reset begins from the rest pose while patterns, sewings and solver parameters are unchanged (every simulated shape key equals its rest key afterwards)
- [x] 8.4 Implement metrics and verify the wall time and the substep and frame counts are present, and that no solver statistic appears when the engine reports none

## 9. Documentation

- [x] 9.1 Write the module documentation and verify a client that can only run Python reaches every entry point from the module itself
- [x] 9.2 Write the shipped reference file and verify every entry point in it matches the text index with the same purpose and units (the probe compares the index against `docs/agent-api.md`)
- [x] 9.3 Document the units, the coordinate spaces, the addressing scheme, the undo granularity and the calls the surface deliberately does not offer; verify by following only that file to prepare, step and read a scene
- [x] 9.4 Write the data-model section (the objects, how they nest, how each is reached, and the supported call for reading and changing each) and verify that following only that section reaches a pattern's vertices, edges and sewings and one simulation mesh object
- [x] 9.5 State that direct Blender access is permitted but discouraged, naming the identity refresh a direct write needs and the failure of skipping it; verify each documented hazard in a scripted session by reproducing the stale identity after an undo and the moved wrapper after a delete (the moved wrapper is the measured `global_uuid != uuid` crash this project already recorded; the undo half needs a session with a viewport)

## 10. End-to-end and validation

- [x] 10.1 Run an end-to-end headless script against the test scene: load, prepare, step a fixed number of substeps, read back, reset; verify the reported counts and that no entry point opened a dialog (50 checks, 0 failures, `tools/probe_agent_api.py`)
- [ ] 10.2 Run the same script in a live session and verify the viewport shows the stepped result and that one undo reverts a scripted pattern batch while leaving the simulated positions alone
- [x] 10.3 Run `openspec validate agent-simulation-api --strict` and fix everything it reports

## 11. Notes from implementation

- The undo push is skipped in a background session instead of being attempted:
  measured, `bpy.ops.ed.undo` refuses to run there ("context is incorrect"), so
  `prepare()` reports `undo_step: False` rather than claiming a step that could
  never be undone. In a session with a window the push is made, once per write.
- `sim.start()` validates the outlines itself before calling the manager, so the
  manager's own refusal path - which reports through a popup in a UI session -
  is never reached from a script.
- The animation toggle (`simulation_with_animation`) still starts through the
  manager; `status()` reports it as `live` because the live mode is read from
  the manager's running flag rather than from this surface's own state.
- `sim.read()` returns the full position arrays (megabytes on a real scene), so a
  caller that only needs numbers should read one pattern at a time.
- Two checks still need a session with a viewport, because they are about undo:
  task 4.1's end-to-end confirmation and task 10.2.
