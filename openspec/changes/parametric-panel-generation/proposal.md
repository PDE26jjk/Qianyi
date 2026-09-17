## Why

Every panel in the add-on is drawn by hand: there is no way to ask for "a pencil
skirt, waist 70 cm, length 60 cm" and get a panel out of it, and no way to
adjust a garment by changing numbers instead of vertices. A parametric,
component-based panel library (borrowing the idea from GarmentCode, without its
code or its dependencies) would let one component produce many designs and
would let generated panels be stitched to hand-drawn ones, because the sewing,
mesh and simulation layers already treat every panel identically.

## What Changes

- Add a Blender-free panel component library (numpy only): curve primitives,
  panel and edge specification, the component protocol, and a deterministic
  noise helper for ragged runs.
- Add panel generators to a project. A generator holds a component id plus a
  parameter block (JSON), produces one or more panels under stable slot names,
  and rebuilds automatically whenever a parameter changes.
- Add a library panel that browses the available components in a grid (thumbnail
  plus name, several per row), filters them by search text and category, shows
  the selected component's details and parameter table, and adds it to the
  project with one click.
- Generated panels are locked against geometry editing (vertices, edges, spline
  points, internal lines, scale), while sewing, simulation, fabric properties
  and 2D placement stay available. Mirror and instance copies remain allowed,
  so one component can generate half of a piece and the user can mirror-copy
  the other half.
- Regeneration preserves edge identity where it can: when the edge list of a
  panel is unchanged, the existing edges are rewritten in place and every
  sewing survives untouched. When the edge list changes, old edges are matched
  to new ones (label first, geometry second) and the surviving sewings are
  re-anchored; sewings whose edge has no match are removed, so no invalid or
  suspended sewing state has to be maintained.
- Add an optional per-component hook so a component that changes its own
  topology can tell the core how its old edges map onto the new ones.
- Let a user keep their own components in folders configured in the add-on
  preferences, reload them without restarting Blender, and see which components
  came from a user folder and which files failed to load.
- Check every panel with the editor's own outline test before writing it, so a
  parameter that would build a self-intersecting or otherwise impossible panel
  is refused with a message and the panels stay exactly as they were.
- Deleting any generated panel deletes its whole group (the sibling panels and
  the generator); detaching converts the whole group into ordinary hand-drawn
  panels.
- Generated panels remain ordinary panels to the rest of the system: the sewing
  data model, mesh generation, simulation bridge and engine contract are
  unchanged.

Not in this change: measurement sources (human body, dog, tent, backpack) are
deferred; parameters are edited by hand. Multi-edge (m-to-n) sewing, a
placement system for bodies, GarmentCode code and third-party dependencies, and
any 2D pattern-editing workflow changes are also out of scope.

## Capabilities

### New Capabilities

- `parametric-panel-library`: Blender-free, deterministic generation of panel
  geometry, edges and edge labels from a parameter block, plus the component
  protocol the library exposes.
- `panel-generator`: parameterized panel sources stored in a project, their
  automatic rebuild, slot naming, group deletion and detach.
- `panel-library-browser`: browsing, filtering and selecting the available panel
  components, and adding one to the project.
- `user-component-library`: loading, reloading and labelling user components
  from folders configured in the preferences.
- `generated-panel-locking`: which editing operations are refused and which
  stay available for panels produced by a generator.
- `sewing-remap`: keeping sewings valid across a rebuild by matching old edges
  to new ones, re-anchoring survivors and removing the rest, including the
  optional component hook that can override the matching.

### Modified Capabilities

None. This repository has no OpenSpec capability yet; every capability above is
introduced by this change.

## Impact

- New code in the add-on: a pure-Python component library, the generator model,
  its operators and UI panel, and guard conditions in the existing 2D editing
  operators.
- Unchanged: the sewing data model (`edge uuid + normalized position`), mesh
  generation, the simulation bridge, the engine contract, and every existing
  hand-drawn-panel workflow.
- No new third-party dependency: the library uses the numpy already bundled
  with Blender.
