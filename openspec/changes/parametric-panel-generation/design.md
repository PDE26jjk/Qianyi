## Context

See proposal.md for the motivation. The constraints that shape this design:

- A panel today is a 2D outline: a closed, counter-clockwise loop of edges over a
  vertex list, plus optional internal lines. An edge with two points and handles
  is a cubic Bezier; an edge with more points is an interpolating cubic spline;
  a two-point edge with vector handles is a straight line. There is no arc
  primitive.
- Panel meshes are sampled from the boundary at the panel's granularity, with
  the boundary points as constraints; a rebuild can map the previous simulation
  results onto the new mesh through barycentric interpolation of the old
  triangles.
- A sewing is stored as `(edge identity, normalized position)` for each side.
  The section list of a panel is closed and linked across edges, so one side of
  a sewing can span consecutive edges.
- The simulation bridge consumes each panel as an independent mesh payload with
  its own fabric, collision layer, grain direction and world matrix; it does not
  know how the panel was created.
- The add-on targets Blender 4.3 (Python 3.11, numpy 2.3.4 bundled) and must not
  gain third-party dependencies; scipy, PyYAML, svgpathtools and cairosvg are
  not available.
- The paradigm is borrowed from the GarmentCode paper; none of its code, data or
  dependencies are used.

## Goals / Non-Goals

**Goals:**

- A Blender-free component library that turns a parameter block into panels,
  with deterministic geometry and deterministic edge labels.
- Generators that own those panels inside a project and rebuild them
  automatically.
- Generated panels that are ordinary panels everywhere else, so they can be
  sewn to hand-drawn panels and simulated through the existing path.
- Sewings that survive regeneration whenever the geometry change permits it.

**Non-Goals:**

- Measurement sources and body fitting (human, dog, tent, backpack). Parameters
  are edited by hand in this change.
- Multi-edge (m-to-n) sewing; today a sewing is one edge to one edge.
- A placement system for garments on a body.
- Hand editing of generated geometry, and any 2D pattern-editing workflow
  change beyond the locks this change introduces.
- Any new curve primitive in the editor, and any reuse of GarmentCode code,
  data or dependencies.
- Batch design sampling or dataset export.

## Decisions

### D1 - Borrow the paradigm, not the code

Components are ordinary Python functions that compute panel geometry from
parameters; the library uses numpy only.

*Alternatives*: vendoring the reference implementation (rejected: pulls scipy,
svgpathtools, PyYAML and cairo into a Blender add-on for a small amount of
geometry), running it in a side process (rejected: a second environment to
install and keep in sync for no functional gain).

### D2 - Generators own ordinary panels

A project gains a generator collection. A generator stores a component id and a
parameter block, and produces ordinary panels that carry one extra field
pointing back at their generator. Sewing, mesh generation, the simulation
bridge and the UI keep working with a single panel type.

*Alternatives*: a separate generated-panel type stored in its own collection
(rejected: property-group collections are single-typed, so a subclass cannot be
stored in the existing panel collection, and a second collection would force
every traversal - sewing, mesh rebuild, simulation setup, UI lists, project
save/load - to handle two sets); generator fields on every panel (rejected: it
couples ordinary panels to this feature).

### D3 - Sewings keep their current storage

A sewing stays `(edge identity, normalized position)` per side. Generated panels
therefore need no new sewing representation and can be sewn to hand-drawn
panels without any change to the sewing layer.

*Alternative*: make a label plus position the identity of a sewing (rejected: it
would change the sewing data model, break the existing editor, and solve a
problem the rebuild path can solve on its own).

### D4 - Edge labels are optional hints

An edge may carry a label. Unlabelled edges get a positional name derived from
the loop order. Labels written by a generator are read-only in the UI and are
used only as a matching hint during a rebuild.

*Alternative*: mandatory semantic interfaces with interchangeability guarantees
(rejected: it forces every component into one garment culture's vocabulary -
waist, armhole, hem - and constrains authors writing other garment traditions
or non-garment products).

### D5 - Library curves reduce to the editor's three representations

The library offers lines, quadratic/cubic curves, arcs and point lists, and each
one reduces to a straight edge, a cubic Bezier edge, or several straight edges.
The editor is not extended.

*Alternatives*: add an arc primitive to the editor (rejected for now: the
approximation error is far below the mesh granularity, so the benefit does not
justify crossing the editor/serialization boundary); keep the library closed to
lines and curves only (rejected: ragged and decorative runs need point lists).

### D6 - No fixed panel origin; stability instead

The library does not impose an origin convention. The requirement it does impose
is stability: a parameter change must not gratuitously translate, rotate or flip
the panel, because the rebuild relies on the new mesh staying close to the old
one for the barycentric transfer of simulation results.

*Alternative*: fix the origin at the bounding-box corner (rejected as
meaningless for components whose natural anchor is elsewhere, and unnecessary
because the placement layer computes the bounding box itself).

### D7 - In-place write first, match and remap second

If a panel's edge list is unchanged, the rebuild rewrites the existing edges in
place and every sewing survives untouched. If the edge list changed, previous
edges are matched to new edges - label first, nearest geometry second - and the
surviving sewings are re-anchored. Sewings without a match are removed; no
suspended or invalid state is introduced.

*Alternatives*: always rebuild and remap (rejected: throws away sewing identity
for the common shape-only change); keep unmatched sewings flagged as invalid
(rejected: a state to maintain, render and explain for no user benefit - the
existing delete path removes sewings whose edge disappeared).

### D8 - Optional component hook with a deliberately small surface

After rewriting a component's panels the system calls an optional hook that can
return nothing (use the default matching), an edge mapping (use it instead of
matching), or a handled marker (the component already adjusted the sewings).

*Status*: validated by the prototype (the notched panel, whose notch parameter
replaces one edge with three). The hook receives a plain-data context - the
previous edges and the rebuilt edges, each as `(panel, index, uuid, label,
sampled points)`, plus whether the edge list changed - and returns `None`, an
edge map, or the handled marker. Components that never change their topology do
not implement it.

*Alternative*: let components manipulate the project's sewings directly
(rejected: it hands Blender data structures to library code and makes the
library untestable outside Blender).

### D9 - One generator owns a group of panels

Panels are addressed by slot name inside a generator, and regeneration reuses
the panel that already holds a slot, so a panel keeps its identity when the
component changes. Deleting any panel of the group deletes the group; detaching
converts the whole group into ordinary panels and removes the generator.

*Alternatives*: one generator per panel (rejected: a garment part is naturally
several panels - a skirt, a bodice with sleeves - and the user would have to
assemble them and hand-stitch the internal seams); per-panel detach or delete
(rejected: partial group states multiply the cases for little gain).

### D10 - Parameters apply immediately

A parameter change rebuilds the panels at once; there is no apply step. The
rebuild is a pure function of the parameter block, so it is cheap and
repeatable.

### D11 - Locking

Generated panels refuse geometry edits (vertices, spline points, edges,
internal lines, scale) and keep everything else: sewing, simulation, fabric
properties, collision layer, grain direction, 2D placement, mirror and instance
copies, and deletion. Detached panels are fully editable.

### D12 - Measurement sources are deferred

Nothing in this change knows about bodies. If a measurement source is added
later, it is a one-shot adapter that writes parameter values; the library and
the generator contract do not have to change for it.

### D13 - Mirror and instance copies are first-class

A component may describe half of a piece and the user may mirror-copy the other
half, so instances participate in the rebuild: they are snapshotted, written and
remapped together with their source panel.

## Risks / Trade-offs

- Hook signature not yet validated -> build the first component that changes its
  own topology before freezing the argument shape; keep the three outcomes as
  the only contract the specs rely on.
- Geometric matching can select the wrong edge on near-symmetric panels -> labels
  take precedence; the fallback is deterministic (nearest boundary point from
  the previous edge's sample points); anything unmatched is removed, which the
  user can re-sew.
- Arc approximation error -> bounded by the four-segment cubic approximation;
  verify visually at the default granularity before declaring the curve set
  final.
- In-place write requires an exact comparison of the edge list -> implement the
  comparison explicitly and fall back to a rebuild when it fails.
- Locking may miss an editing path (scripts, context menus) -> audit the
  operator list as part of the tasks rather than relying on the mode guard
  alone.
- Deleting a group also deletes sewings that joined a generated panel to a
  hand-drawn panel -> this matches the existing delete behaviour; document it.
- Instance chains multiply rebuild work -> accepted, because mirroring is a
  natural authoring workflow.

## Migration Plan

This repository has no OpenSpec root yet; the change creates one and adds an
additive feature.

- No data migration: existing `.blend` files are untouched in format, and
  detached panels are ordinary panels.
- Rollback: remove the generator model, operators and UI; because generated
  panels are ordinary panels, detaching before rollback leaves the user's work
  intact.
- No engine, harness or dependency change is required.

## Open Questions

- Hook argument shape: settled by the prototype (plain-data edge lists plus a
  topology-changed flag); revisit only if a component needs to rewire sewings
  itself rather than mapping edges.
- Whether an arc primitive is worth adding to the editor once generated panels
  are in daily use.
- Whether instance copies should eventually receive their own generator slots
  instead of staying instance links.
- Whether m-to-n sewing, when it arrives, changes the matching rules.
