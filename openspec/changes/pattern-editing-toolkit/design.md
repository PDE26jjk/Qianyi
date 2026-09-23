## Context

See `proposal.md` - Why. Current state that shapes the approach:

- An edge is a pair of vertex indices plus handles and optional interpolation
  points; `Edge2D.update()` turns every kind into sampled points
  (`Qianyi/model/geometry.py`). The engine and the mesh stage only ever see
  those points, so changing how a curve is represented costs nothing on the
  engine side.
- The exact splitting helpers already exist: `split_bezier`
  (`utilities/geometric_operation.py`) and `compute_split_handles` /
  `get_handles_after_split` (`utilities/cubic_spline.py`); the add-vertex tool
  pushes the result to every member of the instance chain
  (`operators/_2d_add_vertex.py`).
- A section is a parameter span of one edge; the seam linker cuts sections at
  proportional length (`calc_sewing_side_sections` / `calc_sewing_sections` in
  `model/sewing.py`) and equalises the segment count across the linked
  sections. It walks one edge run per side today.
- Internal lines are separate edge collections on the pattern, they are
  intersected with the outline (`Pattern.handle_section_intersect`), and the
  parts outside the outline are marked `outsize`.
- Copies share their geometry through an instance chain and an index-aligned
  edit; `_copy_geometry_from` deliberately does not copy internal lines, and no
  copy path re-points sewings today.
- Generators own their panels: `refuse_generated_edit` blocks hand edits, and a
  rebuild remaps sewings by edge label and geometry
  (`generators._remap_sewings`).
- The engine's constrained triangulation does not define a result for edges
  below a length scale, so every command that inserts points has to keep the
  geometry above that scale - see D5.

## Goals / Non-Goals

**Goals:**

- Every command is a model-layer operation, so the operator and `qyapi`
  produce the same panel and the same report.
- Every command is one undo step and leaves the panel in a state the mesh
  stage and the simulation accept (valid outline, sections recreated, sewings
  re-pointed or reported).
- Curves are handled by one rule everywhere: measure along arc length, write
  the result back as points. No command depends on the representation it found.
- Reuse the existing splitting, section-linking and remapping machinery rather
  than adding parallel paths.
- No engine change.

**Non-Goals:**

- A general 2D boolean or offset engine. The cut, the offset lines and the fan
  use the existing intersection handling plus the loop removal in D9 and are
  allowed to refuse a case they cannot do cleanly.
- Nine-point or curvature-continuous corner tools, and a full constraint
  sketcher.
- Resampling a panel to a quad mesh; that is an engine-side mesh change.
- Pleat commands. A fold or a sewn pleat needs the engine to carry an angle on
  an internal line, which it does not do yet; pleats get their own change once
  that exists.
- A seam side whose spans lie on more than one panel, and therefore a
  three-panel junction seam. Both sides of a seam are on one panel each.

## Decisions

### D1. Commands live in the model layer

Each command is a function on the project or the pattern - the shape
`add_internal_line` and `copy_pattern` already have - and the operator is a thin
interactive wrapper that calls it inside one undo step. The script surface calls
the same function.

*Alternative:* implement inside the operators. Rejected: `qyapi` would then have
to reimplement the geometry, which is the drift the current code avoids by
construction.

### D2. Length is measured along the curve, and the result is written back as points

Every command that divides or reshapes a curve measures positions along the
sampled polyline (arc length), not along the control polygon. A cut at a
fraction of the length is found by inverting the sampled arc length, which is
why dividing a 100 mm edge into four gives four 100/4 mm pieces whatever the
curve looks like.

The pieces are written back through D4: a straight piece stays a two-point
straight edge, a piece that has an exact form (a circular arc) keeps that form,
and every other piece becomes a cubic spline fitted through a few control
points. The exact split helpers are used where they are exact, but they are not
the contract: the contract is that the written geometry stays within the
fitting tolerance of the geometry that was there before.

*Alternative:* keep the exact sub-Bezier of `split_bezier` as the result of
every division. Rejected: the pattern then holds a mixture of representations
whose behaviour under the next command differs, which is what makes edge
editing unpredictable in the first place.

### D3. A curve is edited by dragging it, not by arc parameters

The curve tool drags a point on an edge and the edge is fitted through where the
pointer went; it is not a circle and stores no centre, radius or sweep. There is
no arc data type, no arc parameter block, and dragging a handle never has to
"clear" anything.

An arc that a command does produce exactly (the fillet's tangent arc, the fan's
outer arc) is a Bezier that happens to reproduce that circle, which is the one
case where the Bezier form is kept.

*Alternative:* store centre/radius/sweep on the edge and lower it through the
panel library's `Arc`. Rejected: it adds a third representation for a case the
user describes as "just a curve", and it makes every later edit a question about
which of the two owners of the shape is in charge.

### D4. Fitting follows one documented rule

Fitting is `sample by arc length -> choose control points -> check the error`.
The tolerance and the maximum control point count are project constants written
in code (D5 has the same shape) and are deliberately independent of the panel's
granularity: granularity is a meshing ceiling, not a drafting tolerance. When no
fit reaches the tolerance within the control point cap, the command keeps the
closest fit it found and reports that it could not do better, rather than
refusing the edit or silently dropping accuracy.

### D5. A merge threshold, not the mesh density, keeps the geometry legal

Near-coincident points are what break the triangulation, so the project carries
one merge threshold (a constant in code for now, like the fitting tolerance).
A point the user's edit produces closer than the threshold to a point that
already exists merges with it instead of being created; a division whose pieces
would be shorter than the threshold reduces its part count and says so. The
threshold is reported in the command result whenever it changed what the user
asked for, and it is never applied by silently repairing existing files.

### D6. A corner is rounded, chamfered or hollowed

The command takes one selected *vertex* (a point in the middle of an edge is not
a corner). With `theta` the interior angle between the two adjacent edges and
`r` the requested radius, the tangent length is `t = r / tan(theta / 2)`; the
corner vertex moves `t` along the first adjacent edge, a new vertex is placed `t`
along the second, and the two are joined by an edge. `ROUND` joins them with the
tangent arc (the corner material is removed), `CHAMFER` with a straight edge, and
`CONCAVE` with the arc mirrored to the other side of the chord, which cuts a
hollow into the panel: the mirrored arc lies between the chord and the panel, so
the corner loses the whole circular sector rather than only the sliver outside
the tangent arc. The largest radius is the one whose tangent length still fits
both adjacent edges - half of an edge when both of its ends are being treated -
and a radius beyond it is refused with that limit named.

The radius is dragged interactively and can be changed afterwards in Blender's
adjust-last-operation panel. Several selected vertices are treated in one run
when their tangent lengths do not overlap; when they would, the command refuses
and names the vertex, so a run never produces a degenerate edge.

The command is a toolbar tool as well as a menu entry: the tool clicks the
corner under the pointer, shows that vertex while the pointer is over it, and
carries its own setting for which of the three treatments a click applies. A
click that lands on a vertex already in the selection treats that whole
selection; a click on another vertex treats just that one.

A reflex corner is treated by the same rule: the two tangent points sit the same
tangent length along the two edges, and the arc between them is the one on the
notch's side, so the panel gains the figure a convex corner would have lost. The
smallest radius is the one whose tangent length still clears the merge
threshold. The largest is what the two adjacent edges allow, cut back to the
largest one whose outline stays simple - found by bisection, because the
crossing test samples the candidate outline - and cut back again so each trimmed
edge keeps an edge margin at the end the tangent point reaches. The margin is
5 mm, or the panel's own sampling size when that is longer.

The command performs no merge, and that is deliberate. Two measurements say why.
A tangent point that reaches the far vertex of its edge has nothing left of that
edge, so the old behaviour deleted the vertex and one edge; every reference the
app caches - the uuid map the commands and the drawing resolve objects through,
the renderers, the selection, the hover - is keyed to the collection entries such
a removal shifts, and the editor then reads data that moved: the session logs
`obj.global_uuid != uuid` on every draw, and a read through a wrapper whose
storage is gone is the `EXCEPTION_ACCESS_VIOLATION` the maintainer hit. A piece
below the margin is not something the rest of the pipeline can take either: the
engine's sampler never returned on the outline a 3 mm piece produced, while 4 mm
was the shortest that did. The command therefore stops short of both, leaves the
outline's topology alone, and reports the radius it wrote.

*Alternative:* allow only one vertex per run. Rejected as the fallback, not as
the behaviour: it is what happens when the overlap check fails, not what the
common case should feel like.

### D7. Extend is a pivot fan, not a tangent arc

The command takes two points on the outline: the pivot `A` and the target `B`,
with `r = |AB|`. The chord `A B` divides the panel into two halves. The half on
the chosen side of the radius rotates rigidly about `A` by the requested angle,
which starts at zero and only opens (there is no negative angle and therefore no
shrinking), and the material that opens between the radius and its rotated image
is the sector with apex `A`, radius `r` and that angle. The new outline is the
stationary half's outline, the rotated half's outline, and a new arc edge
centred on `A` with radius `r` running from `B` to the rotated image of `B`; the
area grows by `r^2 * theta / 2`.

The two radii are construction lines, not drawing elements: no internal line is
created for them. The command is refused when `A` or `B` is not on the outline,
when the chord crosses the outline, or when the result crosses itself.

The two points are taken by a toolbar tool - nothing is selected first, because
the gesture names its own targets - and the tool draws the point a click would
take, snapping to a vertex within a few pixels so a pivot on a corner is exact.

*Alternative:* extend by a tangent arc whose sweep follows the neighbouring
edges. Rejected: the maintainer's description of the tool is the pivot fan, and
the two are not interchangeable - the fan adds a measured sector, the tangent
arc only reshapes a corner.

### D8. The internal-line cut is a boundary rewrite, not a boolean

The cut walks the outline and the internal line from one crossing to the other
and emits two closed loops, reusing the crossing data the intersection pass
already computes. It applies when the internal line crosses the outline exactly
twice; one crossing, three or more crossings, and a line that does not cross at
all are refused with the reason. A closed internal line that lies inside the
outline is not a cut - it is already a hole through the `is_hole` flag - so the
cut leaves it alone rather than inventing a second meaning for it.

The two panels inherit the source's fabric, granularity, grain, collision
layer, state and generator link, and they join the source's instance chain so a
linked panel stays linked. The cut edge is available as a seam through an
explicit option that is off by default: not every cut is meant to be sewn shut,
and a panel that is meant to be sewn can also be sewn afterwards with the
ordinary sewing tool.

*Alternative:* a polygon-clipping library. Rejected: no third-party dependency
is allowed in this add-on (Blender's numpy only).

### D9. Offsets are de-looped, and the ends are the user's choice

Internal lines are repeated from a source line by a signed distance along the
local normal, `N` lines at a time. Because an offset beyond the local radius of
curvature, or past a concave corner, produces a self-crossing polyline, the raw
offset is de-looped before it is used: the self-intersections are found, the
loops they enclose are removed, and the surviving skeleton is what is kept. The
visible cost is that an offset line can be shorter than its source, and a line
that degenerates completely is dropped and reported. A self-crossing internal
line is not an acceptable result in any mode, because the in/out classification
of its sections and the seam sampling both assume a simple curve.

What happens at the ends is a mode: `CLIP` trims the line to the outline,
`EXTEND_TO_OUTLINE` projects both ends onto the outline, and `KEEP` leaves the
line as the offset produced it. `EXTEND_TO_OUTLINE` targets the outline only;
intersecting or extending against other internal lines is left for later.

### D10. Pleats wait for the engine

Folding an internal line needs the engine to carry an angle on that line; the
current engine has no such concept, so a pleat command would have to fake it
through geometry that the simulation then undoes. The pleat commands are
therefore out of this change and get their own once the engine-side angle
exists.

### D11. Many-to-many keeps two sides, each a set of drawn spans

A seam still has exactly two sides. Each side is a *set* of spans, where a span
is what today's one side already is: an edge run on one panel with a start and
an end position and a direction. The spans of a set are given in drawing order
and carry the direction they were drawn in, so they need not be geometrically
contiguous or ordered; the set's sections are the concatenation of its spans'
sections, and the matching is the existing two-way proportional merge over the
two concatenated lists, which is what the section linker already implements.

Because a set lives on one panel, a seam still joins exactly two panels, so the
payload stays the existing two-pattern stitch group and no payload
decomposition is introduced. A span that can no longer be resolved drops out
and is reported, and a set left with no spans is reported as incomplete instead
of stitching nothing. The length tolerance that decides "matched" and "unmatched"
is a project constant to be calibrated by experiment (see Open Questions).

The interaction follows the free sewing tool: draw the spans of the first set,
press Enter to finish it, then draw the spans of the second.

*Alternative:* make a seam an N-sided object with a general matching graph, or
let one set span several panels. Both are rejected for this change: the first
needs a branching rule nobody has defined, and the second reopens the section
linker for a junction case that is rare next to the long-edge-to-several-short
one.

### D12. Only a plain copy carries seams

An instance or a mirror copy brings no seams with it: the copy exists to be
edited in step with its source, and a seam that silently appeared on every
member of the chain would multiply the stitches the user asked for. A plain copy
can carry the seams whose two sides both lie inside the copied selection, by
re-pointing them through the copy's uuid map, which is the same map shape the
generator rebuild uses; a seam that crosses the selection boundary is reported
and left alone. Internal lines are copied by default with an outline-only
option, and flipping a panel in place is a real geometry mirror (its own
outline), not an instance.

### D13. The editor keeps its modes

A unified selection model - one selection holding panels, edges, vertices and
sewings together, with the mode reduced to a hit-test filter and a panel that
adapts to what is selected - was considered and rejected. The modes are kept
because they make "what can this click mean" unambiguous, keep every operator's
`poll` a one-liner, and keep the script surface's "address an object by name"
contract simple. What this change removes instead is the *cost* of the modes:
see D14 and D15.

### D14. A tool activates its own mode

Picking a tool is a statement of intent, so a tool puts the editor into the mode
it works in, both from the toolbar (its `draw_cursor`) and from the operator
itself (`invoke`, or `setup_state_machine` for the modal tools). The mode check
comes out of those operators' `poll`, and `ensure_edit_mode()` in
`model/qianyi_data.py` is the one place that writes the two properties.

Before this, a tool's `draw_cursor` set only the *sub* mode while its operator
required the matching top-level mode, so picking "add vertex" in the pattern
mode did nothing at all - the failure mode this decision removes.

### D15. Geometry commands are re-runnable, so Blender's redo panel works

Blender's own descriptions of the two operator options are the contract:
`REGISTER` is "display in the info window and support the redo toolbar panel",
and `UNDO` is "push an undo event when the operator returns `FINISHED` (needed
for operator redo)". The panel's widgets are the operator's RNA properties, and
changing one makes Blender roll the operator's own undo step back and run
`execute()` again.

So a command is written to satisfy three things:

1. **the target comes from the selection, not from where the pointer was** -
   the undo step restores the selection, so a re-run finds the same target
   without the operator having to store an identity; hover only decides what a
   click *selects*;
2. **`execute()` recomputes the result from the state before the operation**,
   from the semantic parameters, and the commit writes the resolved values back
   into those parameters; the modal path and the re-run path are the same code;
3. **derived work is derived, never incremental** - a topology change remaps the
   sewings that referenced the changed edges by recomputing from the
   pre-operation edges (label first, geometry second, exactly as the generator
   rebuild already does), and drops what it cannot remap with a report.

The pen tools, the sewing tool, box select and the 3D pick are exceptions: their
"parameters" are the gesture itself, so there is nothing for a redo panel to
adjust. They keep working as they do today.

A tool click is the second exception, and it needs the identity the first rule
avoids: the operator runs before any selection step exists, so it takes the
element under the pointer and carries it in its own properties - the panel and
the vertex for the corner, the panel and the two points for the fan. Blender
rolls the operator's own undo step back before a re-run, and that step includes
the selection the operator made, so the selection cannot be the target: the
stored identity is what the redo panel re-runs from. The gesture itself is
press, drag, release - the drag sets the number, the release applies it, and a
click that never moved applies the value the drag started from.

The redo panel cannot know what range a corner accepts, so a value dragged past
the top is clamped to it and written back to the operator's own property: the
panel ends up showing the radius that was applied, and no run of the command
reports a radius that does not fit. A value below what the corner can take is
not clamped up but read as zero - there is nothing to treat - so the run does
nothing and reports nothing rather than failing.

A gesture draws what it has as it goes. The tool's own cursor preview answers
"what would a click take"; once the gesture is running it owns the preview and
draws the points it has taken, the radius it is measuring (with an arrowhead)
and **the outline the command would leave behind**, taken from the same
candidate the self-crossing test uses. The arc on its own does not say what the
panel becomes; the resulting outline does, and it is the same assembly for every
command, so the preview cannot drift away from what is written.

The click that activates a tool is the first step of its gesture rather than a
click spent starting it: for the fan, the click that picks the tool is the
pivot, so the gesture reads pivot, target, angle. Only the step that needs the
pointer to itself is modal - for the fan that is the angle, which starts on the
click that took the target and applies when the drag is released - so the view
can still be orbited and panned while the points are being chosen.

A renderer is kept in the temp data of the object it draws, and Blender hands
that data to the next object added over a removed one. A renderer therefore
carries the identity it was made for and is checked against its owner before it
is used; one that was inherited is replaced rather than used, which is what a
fan run crashed on in a windowed session (the strict identity lookup inside the
renderer raised) while a background session never reached it, because a
background session has no renderers at all.

*Alternative:* a custom "last operation" panel with the parameters and target
uuids kept as scene state and a manual undo-and-replay. Rejected: it would not
answer F9, it duplicates what Blender tracks per operator, and the maintainer
asked to stay with Blender's habits.

### D16. Re-runnable commands must not trust caches that undo does not restore

Undo restores Blender data, not this add-on's Python-side caches: the identity
map (`global_data.uuid2obj`) and every `define_temp_prop` value survive a roll
back as they were. A re-run therefore starts by refreshing identities
(`refresh_all_uuids` / `refresh_collection_uuid`) and by rebuilding derived data
through `forced_update()`, which is the same rule the script surface already
follows after an undo.

## Risks / Trade-offs

- [Fitting replaces exact geometry, so repeated edits can drift] -> every
  command fits against the geometry that was there before it ran and reports
  when it could not reach the tolerance, so the error per command is bounded by
  a project constant rather than by the number of edits.
- [The merge threshold silently moves a point the user placed] -> the command
  reports every merge, and the threshold is a constant the user can be told, so
  the behaviour is explainable rather than mysterious.
- [A fan or a fillet produces an outline that crosses itself] -> the command
  validates the result before it commits and refuses with the crossing point,
  leaving the panel intact.
- [Offset lines lose material where the source curves tighter than the offset
  distance] -> the de-looping is the documented behaviour, and a line that
  degenerates completely is reported rather than kept as a tangle.
- [The many-to-many tolerance is wrong in either direction: too loose hides a
  real mismatch, too tight refuses a seam that should match] -> the tolerance is
  one constant, reported with the unmatched remainder, and calibrated by the
  experiment in the task list instead of being guessed here.
- [The cut's optional seam duplicates a seam the user creates by hand right
  after] -> the option is off by default, and the report names the seam it
  created so a duplicate is visible in the seam list.
- [A cut panel joins the source's instance chain, so an edit to one half is
  applied to the other] -> that is the meaning of a linked panel; a user who
  wants two independent halves detaches them first, which is already how a
  generated panel becomes editable.

## Migration Plan

Purely additive; the only behaviour change to an existing file is that a plain
copy now brings internal lines with it, which is the documented default of the
new option. Rollback is reverting the change. Panels created by the new commands
are ordinary panels with ordinary edges, internal lines and seams - every curve
ends up as points, handles or interpolation points the current build already
understands - so a file saved by this change opens in an older build with its
geometry intact.

## Open Questions

- The many-to-many length tolerance: which value makes "200 mm sewn to 120 + 80"
  match while a genuinely short side is still reported unmatched? Decided by the
  experiment in the task list, not by this document.
- Multi-mirror instances: several programs allow a single mirror instance so a
  symmetric seam can be maintained; this project allows a chain with several
  mirrors. Whether the chain should stay that way is a separate discussion, and
  this change does not touch it.
- Whether the rectangle and circle should also be reachable from a "primitive"
  submenu in the add tool rather than only from the library browser; a UI
  placement question that does not change the specs.
- Whether an exactly-representable arc should also be offered as an export type
  (DXF bulge) when the export path is extended; deferred until an export format
  exists.
