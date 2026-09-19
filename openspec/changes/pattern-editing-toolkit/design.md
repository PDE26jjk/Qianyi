## Context

See `proposal.md` - Why. Current state that shapes the approach:

- An edge is a pair of vertex indices plus two handles and optional
  interpolation points; `Edge2D.update()` turns every kind into sampled points
  - `Qianyi/model/geometry.py`. The engine and the mesh stage only ever see
  those points, so a new curve kind costs nothing on the engine side.
- Splitting a curve already exists for the "add vertex" tool:
  `split_bezier` (`utilities/geometric_operation.py`) and
  `compute_split_handles` / `get_handles_after_split`
  (`utilities/cubic_spline.py`), and the operator that uses them pushes the
  result to every member of the instance chain (`operators/_2d_add_vertex.py`).
- A section is a parameter span of one edge; the seam linker already cuts
  sections at proportional length (`calc_sewing_side_sections` /
  `calc_sewing_sections` in `model/sewing.py`, with a `blur_factor` tolerance)
  and equalises the segment count across the linked sections.
- Internal lines are separate edge collections on the pattern, they are
  intersected with the outline (`Pattern.handle_section_intersect`), and the
  parts outside the outline are marked `outsize`.
- Copies share their geometry through an instance chain and an index-aligned
  edit; `_copy_geometry_from` deliberately does not copy internal lines, and no
  copy path re-points sewings today.
- Generators own their panels: `refuse_generated_edit` blocks hand edits, and a
  rebuild remaps sewings by edge label and geometry
  (`generators._remap_sewings`).

## Goals / Non-Goals

**Goals:**

- Every command is a model-layer operation, so the operator and `qyapi`
  produce the same panel and the same report.
- Every command is one undo step and leaves the panel in a state the mesh
  stage and the simulation accept (valid outline, sections recreated, sewings
  re-pointed or reported).
- Reuse the existing splitting, section-linking and remapping machinery rather
  than adding parallel paths.
- No engine change.

**Non-Goals:**

- A general 2D boolean/offset engine. The cut, the offset lines and the pleats
  use the existing intersection handling and are allowed to refuse a case they
  cannot do cleanly.
- Nine-point/curvature-continuous corner tools, or a full constraint sketcher.
- Resampling a panel to a quad mesh; that is an engine-side mesh change.
- Automatic pleat layout from a garment template (the pleat command takes the
  positions it is given).

## Decisions

### D1. Commands live in the model layer

Each command is a function on the project or the pattern - the shape
`add_internal_line` and `copy_pattern` already have - and the operator is a thin
interactive wrapper that calls it inside one undo step. The script surface calls
the same function.

*Alternative:* implement inside the operators. Rejected: `qyapi` would then have
to reimplement the geometry, which is the drift the current code avoids by
construction.

### D2. Division splits the curve, it does not resample it

Inserting a point splits a Bezier with `split_bezier` and a spline with
`compute_split_handles`, exactly as the existing add-vertex tool does, and the
same insert is applied to every member of the instance chain. A second division
of the same curve therefore reproduces the shape, which resampling would not.

### D3. An arc keeps its parameters on the edge, realised as a Bezier

The panel library already has an arc (`panellib/curves.Arc`, a bulge) which is
lowered to Bezier edges when a panel is landed, and its test pins that
approximation at 0.05 mm. The editor therefore follows it rather than
introducing a second representation: the edge keeps the arc's
centre/radius/start-angle/sweep (or the three points, normalised on commit) as
parameters, and its geometry is the Bezier the existing `Arc` produces. Radius
and sweep editing writes the parameters and regenerates the handles, so the
stored parameters stay the single source for an arc; dragging a handle clears
the parameters and turns the edge into an ordinary Bezier, which is the honest
answer to "the user has reshaped it".

*Alternative:* a new `arc` edge kind sampled directly from the circle.
Rejected: it duplicates what the library already does, it adds a third
representation to `Edge2D.update()` and to the export path, and the 0.05 mm
approximation is two orders below the panel's sampling tolerance.

### D4. The internal-line cut is a boundary rewrite, not a boolean

The cut walks the outline and the internal line from one crossing to the other
and emits two closed loops, reusing the crossing data the intersection pass
already computes. The two panels inherit the source's fabric, granularity,
grain, collision layer, state and generator link. No general polygon boolean is
introduced.

*Alternative:* a polygon-clipping library. Rejected: no third-party dependency
is allowed in this add-on (Blender's numpy only).

### D5. Pleats are expressed with primitives that already exist

A fold line is an internal line; a sewn pleat is a seam between two such lines.
So the pleat command writes internal lines and seams and reports the take-up; it
adds no engine concept and no new geometry type. This also means a pleat can be
edited afterwards with the ordinary internal-line and seam tools.

*Alternative:* a dedicated pleat data type that the mesher understands.
Rejected: it would need the engine's mesh stage to know about pleats, which
contradicts the "the engine does not care how a panel was created" contract.

### D6. Many-to-many keeps two sides and N spans

The seam stays a pair of sides; each side is an ordered list of spans, and the
matching is the section linker's proportional mapping, which already exists.
The payload is decomposed per panel pair, so a junction seam contributes two
stitch groups. This is the smallest change that covers the real cases (a long
edge to several short ones, a yoke to two fronts) and it keeps the UI, the undo
stack and `qyapi` on one object.

*Alternative:* make a seam an N-sided object with a general matching graph.
Rejected for this change: it needs a matching rule for branching that the
competitor semantics do not define either, and it would reopen the section
linker.

### D7. Copying re-points sewings through an explicit uuid map

The copy builds a map from the source edges' uuids to the copies' edges as it
creates them, and duplicates a seam only when both of its sides' spans are in
that map. This is the same map shape the generator rebuild already uses, and it
is why a duplicated seam can be reported precisely when it was skipped.

## Risks / Trade-offs

- [An arc's parameters and its handles disagree after an edit that was not made
  through the parameters] -> the rule is that any handle drag clears the
  parameters, so an edge either has arc parameters and generative handles or is
  an ordinary Bezier, never both claiming to be in charge.
- [The cut produces a panel that fails the self-intersection check] -> the cut
  validates both resulting outlines before it commits and refuses otherwise,
  leaving the source panel intact.
- [Offset internal lines cross each other on a curved source line] -> offsets
  are clipped to the outline and a generated line that is fully outside is
  reported and dropped; the command reports what it dropped rather than
  silently producing a tangle.
- [Pleat params that fit the width but violate the mesh tolerance] -> the
  validation in the spec refuses a fold spacing below the panel's mesh
  tolerance before anything is written.
- [Proportional mapping hides a genuine length mismatch] -> the seam reports the
  largest unmatched remainder and the length difference, and an unmatched seam
  does not stitch until the sides agree.
- [Copying seams duplicates a seam twice when several panels are copied as a
  group] -> the seam is duplicated once per copy operation, keyed by the
  selections it touches, and the task list covers copying a pair as a group.

## Migration Plan

Purely additive; the only behaviour change to an existing file is that a copy
now brings internal lines with it, which is the documented default of the new
option. Rollback is reverting the change. Panels created by the new commands are
ordinary panels with ordinary edges, internal lines and seams, and an arc is a
Bezier with extra parameters, so a file saved by this change opens in an older
build with its geometry intact (the arc parameters would be ignored and the
edge edited as the Bezier it is).

## Open Questions

- Whether the rectangle/circle should also be reachable from a "primitive"
  submenu in the add tool rather than only from the library browser; that is a
  UI placement question and does not change the specs.
- Whether `arc` should also be offered as an export type (DXF bulge) when the
  export path is extended; deferred until an export format exists.
