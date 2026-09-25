## Why

An agent that starts from a blank file cannot do anything today. Measured: on an
empty scene `qyapi.state()` reports no project and every pattern call refuses with
"this scene has no project", and a script cannot make one either - the obvious
creation leaves the project and its default fabric without identities, so the
first `patterns.create` raises an `AssertionError`, and the project's own name
stays empty while the node tree carries another one, so the UI and the surface
disagree about what a project is called. The second half is the shape of a
build: laying out a pattern step by step passes through outlines that cross, and
every geometry write refuses that, so a caller cannot take the intermediate step
the work needs.

## What Changes

- Add a `qyapi.projects` group: list, create, activate, rename, remove and
  "which one is active".
- Make `create` produce a project that is immediately usable: the node tree, the
  identities of the project and of its default fabric, the names, and the active
  index - the four steps a caller has to perform by hand today, one of which is
  invisible until it fails.
- Keep a project's two names in step: the node tree's own name, which the
  Project panel lists, and the add-on's name property, which every call
  addresses. Creating and renaming set both; listing and `state()` report both.
- Add a per-call `allow_crossing=False` to the geometry writes, so a caller that
  is building a shape may leave an outline that crosses itself for a step.
- Report a crossing outline in every answer that produced one: the validity, the
  crossing point, and whether the pattern's mesh is now stale because the mesh
  stage refused to rebuild it.
- Keep the rules that do not bend: a crossing outline is never handed to the
  mesh sampler, never starts a simulation, and the read-only outline check still
  reports without raising. The scene's own Check Self-Intersection switch stays
  what it is - a switch for the interactive operators - and the surface does not
  read or write it.

Not in this change: any session-wide or global switch for crossing outlines (the
flag is per call), project templates or duplication, a body or measurement
source, m-to-n sewing, new UI, and any engine or DP backend change.

## Capabilities

### New Capabilities

- `agent-project-management`: listing, creating, activating, renaming and
  removing projects from a script, and the identity and naming work a project
  needs before any other call can work on it.
- `agent-outline-crossing-policy`: the per-call option that lets a geometry write
  leave a crossing outline, what such a call reports, and the limits that stay in
  force.

### Modified Capabilities

None. The capabilities this change extends live in changes that are still open
(`agent-pattern-api`); nothing has been archived into `openspec/specs/` yet, so
there is no main spec to modify. The existing behaviour is restated in the new
capability's requirements where it must not change.

## Impact

- New code: a `projects` submodule of `qyapi`, a per-call flag on seven
  `qyapi.patterns` writes, the reporting they return, and the documentation of
  both.
- `qyapi/patterns.py` and `qyapi/_address.py`: the outline check becomes
  conditional, and the results gain the validity, the crossing point and the
  mesh-stale flag.
- Unchanged: the pattern, sewing and mesh data models, the `.blend` format, the
  interactive operators and their switch, the simulation surface, and the engine
  contract.
