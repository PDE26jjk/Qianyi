## 1. Shared curve rules and precision

- [x] 1.1 Add the project constants for the fitting tolerance, the control
  point cap and the merge threshold (in code, documented in `LOCAL_DEV.md` only
  if a value turns out to be machine-specific) and state in the docstring why
  they are independent of a pattern's granularity
  (`Qianyi/model/pattern_geometry.py`: `FIT_TOLERANCE_MM` 0.05 mm,
  `FIT_MAX_CONTROL_POINTS` 12, `MERGE_THRESHOLD_MM` 0.5 mm, all three in the
  module docstring's drafting-versus-granularity paragraph)
- [x] 1.2 Add the arc-length sampling and fitting helper: sample a curve by arc
  length, fit control points within the tolerance and the cap, return the
  closest fit with a flag when the tolerance was not reached, keep a straight
  piece straight and an exactly-representable piece as a Bezier
  (`Qianyi/utilities/curve_fit.py`: `cumulative_length`, `point_at_length`,
  `resample_by_arc_length`, `slice_by_arc_length`, `fit_control_points`
  returning `(control_points, reached, error)`)
- [x] 1.3 Add the merge helper: merge a produced point with an existing point
  closer than the threshold, and reduce a part count that would produce pieces
  shorter than it, reporting both
  (`pattern_geometry._keep_positions` / `_too_close` / `_point_on`, reported as
  the `merged` and `capped` fields of the command report)
- [x] 1.4 Verify a divided Bezier stays within the fitting tolerance of the
  original, that dividing it twice matches dividing it once within the same
  tolerance, that a divided straight edge is exactly straight, and that a cut
  point landing inside the merge threshold reuses the existing vertex
  (`blender -b --factory-startup --python .agents/scratch/check_pattern_geometry.py`:
  the three pieces of a curve stay within 0.073 mm of the source when measured
  independently of the fitter, dividing twice differs from dividing once by
  0.050 mm, a divided straight edge deviates 0.000 mm, and a cut 0.5 mm from an
  existing vertex reuses it with the part count capped and reported)

## 2. Edge division

- [x] 2.1 Add the model-layer divide function for an edge or an edge chain
  (wrap over a whole outline), dividing by arc length with the fitting and merge
  rules of group 1
  (`pattern_geometry.divide_edges` / `plan_divide`; a selection is divided edge
  by edge, not as one long edge - joining is a different command)
- [x] 2.2 Add the target-length mode: distance plus cut count (default one,
  capped at what the selection holds), a point every distance along the arc
  length, the last piece absorbing the remainder, with the achieved lengths, the
  remainder and the cap in the report
  (checked: 30 mm cuts over 100 mm give `[30, 30, 30, 10]`, and the count is
  capped at what the edge holds - a 30 mm cut on a 20 mm edge is refused)
- [x] 2.3 Apply a division to every member of the instance chain and verify the
  members stay index-aligned
  (`_chain_members` / `_divide_member`; the check divides one pattern of a linked
  pair and both members keep the same eight piece lengths)
- [x] 2.4 Add the operator and workspace tool for both modes, with live preview
  of the inserted points, and verify one undo step removes them
  (`Qianyi/operators/_2d_divide_edge.py`, in the pattern editor's context menu
  and not as a toolbar tool: the maintainer asked for the menu, and there is no
  live preview - the numbers are the operator's own properties and the command
  opens the adjust-last-operation panel itself, because a run from a context
  menu has neither F9 nor the Edit menu entry in front of the user. One run is
  one undo step; the maintainer verified the pattern and the re-run in a live
  session, and `.agents/scratch/check_divide_operator.py` covers the selection
  rule headless)

## 3. Corner tools

- [x] 3.1 Implement the corner command with `ROUND`, `CHAMFER` and `CONCAVE`:
  tangent length from the interior angle, two points on the adjacent edges
  joined by an arc, a straight edge or the mirrored arc, with the corner
  material removed or added as the mode says
  (`pattern_geometry.corner_vertices` / `plan_corner` / `_corner_arc`, checked
  by `.agents/scratch/check_corner.py`: the tangent length is
  `r / tan(interior angle / 2)`, the arc is written as the Bezier that
  reproduces the circle exactly, a chamfered corner goes straight, and the
  measured area matches the closed form for each mode. `CONCAVE` came out as
  the mirrored arc cutting the whole sector out of the corner rather than
  adding material - the mirrored arc lies between the chord and the pattern - so
  the spec and `design.md` D6 were corrected on that point)
- [x] 3.2 Implement the largest-fitting-radius refusal, naming the limit, and
  allow a corner whose neighbour is a curve by trimming that curve first
  (checked: a 200 mm radius on a 100 mm edge is refused and the hint names
  95.000 mm as the largest that fits - the largest is what the two adjacent
  edges allow less the margin the command keeps at each end it trims, cut back to
  the largest whose outline does not cross itself, found by bisection; a corner
  next to a curved edge is
  handled by trimming that edge's own samples and refitting the piece, which
  comes out as a spline, and the measured trim equals the reported tangent
  length)
- [x] 3.3 Make a multi-vertex run apply when the tangent lengths do not overlap
  and refuse with the vertex named when they do
  (checked: two corners at the ends of one 100 mm edge refuse 60 mm and name
  50.000 mm, then apply at 40 mm in one run with both corner edges added. A
  reflex corner is treated rather than refused: the tangent points sit the same
  tangent length along the edges, the arc lands in the notch, and the pattern
  gains the 21.46 mm2 the figures predict. The command is also a toolbar tool
  with its own setting for which treatment a click applies, and the radius is a
  plain millimetre figure: it used to be a Blender length, which the pattern read
  as metres. The radius a run left behind is brought into the new corner's range
  instead of refusing, and the drag is an offset from that value. At the largest
  radius the command keeps an edge margin on both trimmed edges (5 mm, or the
  pattern's sampling size when that is longer): the outline keeps every vertex and
  every edge it had and gains the one vertex and one edge the treatment adds, so
  a 100 x 100 square corner goes from four vertices and four edges to five of
  each, with the two trimmed edges 5 mm long. It used to merge the tangent points
  into the neighbouring vertices at that limit, which deleted a vertex and an
  edge; that is what crashed the editor - every cached reference is keyed to the
  collection entries such a removal shifts - and it is also what the engine's
  sampler cannot take: on a 100 mm pattern a 3 mm piece never came back from
  `geometry.sample_points`, while 4 mm was the shortest that did. The maintainer
  ruled the triangulation's own behaviour out of scope, so the command stays
  clear of both and `.agents/scratch/probe_corner_crash.py` checks that the
  outline's counts never fall.)
- [x] 3.4 Wire the radius to the drag and to the redo panel, and verify a re-run
  applies the new radius instead of adding a second corner treatment
  (`Qianyi/operators/_2d_corner.py`: a modal drag that takes the radius from the
  pointer's distance to the corner, clamped to the fitting range, drawing each
  arc and its tangent lengths as it would land, with the redo panel opened when
  the drag is confirmed; the operator carries `REGISTER`, `UNDO`, `GRAB_CURSOR`
  and `BLOCKING`, and `execute` recomputes from the selection, so the pattern's
  re-run replaces the treatment instead of adding one. The gesture is press,
  drag, release - the release applies it, and a click that never moved applies
  the radius the drag started from - and the corner it acts on is carried in the
  operator's own properties, because a tool click runs before any selection step
  exists and Blender rolls the operator's own step (including the selection it
  made) back before a re-run. A radius the redo slider pushed past the range is
  clamped to it and written back, so the slider cannot produce a radius that does
  not fit - the pattern is not a place to report that - and a radius below the
  smallest finishes the run with nothing changed, which is what actually takes
  the pattern back to how it was, because a cancelled re-run keeps the last
  result. The preview draws the whole resulting outline, not only the arc.
  Headless checks cover the
  registration and the properties; the drag itself is a live-session check)
- [x] 3.5 Verify the outline is one closed loop after each mode and that a
  result crossing itself is refused with the crossing point
  (checked headless: the outline validates after `ROUND`, `CONCAVE` and a
  two-corner run, and `plan_corner` assembles the candidate outline - trimmed
  edges plus the arcs, in loop order - and refuses a crossing before anything is
  written)

## 4. Pivot fan

- [x] 4.1 Implement the fan: pivot and target on the outline, radius from the
  distance between them, the chord dividing the pattern, the chosen half rotating
  rigidly about the pivot by an angle that starts at zero, the sector filled in
  between the radius and its rotated image, and the new arc edge from the target
  to its rotated image
  (`pattern_geometry.pivot_fan` / `plan_fan` / `_fan_member`, checked by
  `.agents/scratch/check_fan.py`: the half on the right of the radius turns
  clockwise, the arc comes out as the Bezier that reproduces its circle, and the
  measured outline area grows by `radius^2 * angle / 2` to 0.001 mm2. A radius
  that lies along the outline is refused - it does not divide the pattern - which
  the spec now says; the scenario's target moved to another edge, because the
  corner-plus-adjacent-edge case is that degenerate one)
- [x] 4.2 Implement and report the added area, and refuse the cases in the spec
  (a point that is not on the outline, a chord crossing the outline, a result
  crossing itself)
  (checked: a point 50 mm inside the pattern is refused by name and distance, a
  chord that leaves a notched pattern is refused with the point where it meets the
  outline, a closing or wider-than-180-degree angle is refused, and the report
  carries the added area)
- [x] 4.3 Verify no internal line is created for either radius, that the
  stationary half is untouched, and that a seam on a moved edge follows the
  rotation
  (checked: the pattern gains no internal line, every stationary vertex keeps its
  position to 1e-3 mm, and a seam on an edge inside the rotating half keeps its
  edge and its position, so its point lands where the rotation puts it)
- [x] 4.4 Wire the angle to the drag and the redo panel, and verify a re-run
  rebuilds from the pre-operation state with the new angle
  (`Qianyi/operators/_2d_fan.py` and the toolbar tool beside it: a gesture that
  takes the pivot and the target from two clicks on the outline and the angle
  from the drag that follows, applied when the button is released, drawing the
  outline it would leave behind. The pivot and the target are taken by two
  ordinary clicks - no modal, so the view stays usable - and only the angle is a
  modal drag, which starts on the click that took the target and applies when it
  is released. The running gesture owns the preview and draws the pivot, the
  target and the point a click would take in their own colours, the radius
  between them with an arrowhead, and the whole resulting outline; the tool's
  own cursor preview draws the point a click would take and
  snaps to a vertex within a few pixels, so a
  pivot on a corner is exact; it is a toolbar tool and nothing is selected
  first, because the gesture names its own targets. The two points and the angle
  are the operator's own properties, so the redo panel re-runs `execute` from
  the pattern as it was. Registered with `REGISTER`, `UNDO`, `GRAB_CURSOR` and
  `BLOCKING`; the headless checks cover the registration and the properties, and
  the drag itself is a live-session check)


## 5. Curve editing through points

- [x] 5.1 Add the drag tool that fits the edge through the dragged position,
  keeping both ends attached to their neighbours
  (`Qianyi/operators/_2d_curve_fit.py` and `pattern_geometry.EdgeDrag`: a
  `StateOperator` gesture - press takes the edge under the pointer, every move
  bends it, the release writes once. The falloff runs along the curve's own
  parameter and is written in what the edge can express: the two Bernstein
  weights for a line or a Bezier, the control points' own influence for a
  spline, scaled so the point the pointer took lands on the pointer instead of
  near it. Both ends stay pinned, the neighbours are untouched, and a drag that
  only slides along the line leaves it the line it was. Checked by
  `.agents/scratch/probe_curve_drag.py` (the command layer: the form, the ends,
  the neighbours, the pointer point, the remaining mesh) and
  `.agents/scratch/probe_curve_drag_modal.py` (the gesture through the state
  machine: one write per drag, and a hold, an escape or a press off an edge each
  write nothing) - 12 and 14 checks, none failing)
- [x] 5.2 Verify no centre, radius or sweep is stored, that dragging a
  command-produced arc leaves a spline through the dragged points, and that the
  drag reports when the fit could not reach the tolerance
  (there is no arc parameter on `Edge2D` at all: a drag writes two handles or
  the spline's own control points and nothing else. A corner's arc is already a
  Bezier, so dragging one writes handles; a spline edge keeps its control
  points, count included. A Bezier that cannot follow the pointer exactly has
  nowhere to say so that the user would understand, so the drag keeps its
  numbers in the console log - how far the curve ends up from the pointer - and
  never reports. The same script measures one mouse move at 0.57 ms for a
  straight or Bezier edge and about 1 ms for a five-point spline, against a
  16.7 ms frame: the projection is solved over a slice of the base and the
  preview is staged through the pattern's matrix once for the whole curve)

## 6. Rectangle and circle primitives

- [ ] 6.1 Add the rectangle component with its parameter schema and verify the
  placed outline area and the stable edge labels across a rebuild
- [ ] 6.2 Add the circle and annulus components and verify the hole is honoured
  by the mesh stage
- [ ] 6.3 Verify a placed primitive rebuilds in place with its sewings
  remapped, and that the rebuild report names anything it could not rebuild
- [ ] 6.4 Verify detaching a primitive yields an ordinary editable pattern

## 7. Internal line tools

- [ ] 7.1 Implement the cut along an internal line that crosses the outline
  exactly twice, validating both resulting outlines before committing, and
  verify the two patterns' areas sum to the original
- [ ] 7.2 Implement the refusals (no crossing, one crossing, three or more
  crossings, a closed line inside the pattern) and verify each names its reason
- [ ] 7.3 Verify both halves join the source's instance chain, the cut's
  property inheritance and its sewing remap, including the report for a sewing
  that had to be dropped
- [ ] 7.4 Implement the optional seam along the cut and verify it is off by
  default, that when it is on the report names the seam it created, and that a
  cut without it leaves the seam list unchanged
- [ ] 7.5 Implement converting a run of outline edges into an internal line
  (chord re-route), with the whole-outline and chord-crossing refusals
- [ ] 7.6 Implement repeated internal lines at a signed distance with the three
  end modes, and verify the offset placement on both sides of the source line
- [ ] 7.7 Implement the offset de-looping (self-intersection removal) and verify
  a concave corner, a tight concave arc and a fully degenerate offset each
  produce the documented result and report
- [ ] 7.8 Allow an internal line to be a sewing side and verify a dart sewn to a
  run of outline edges stitches and closes

## 8. Many-to-many sewing

- [ ] 8.1 Extend the seam model so each side holds a set of spans (a span being
  today's run: a pattern, an edge index, a position range and a direction), and
  verify an existing one-to-one seam reads back unchanged
- [ ] 8.2 Build a side's sections by concatenating its spans' sections in order
  and verify a set whose spans are not geometrically contiguous matches end to
  end
- [ ] 8.3 Implement the proportional two-way merge over the concatenated
  section lists and verify a 200 mm side pairs with spans of 120 mm and 80 mm
- [ ] 8.4 Run the calibration experiment for the length tolerance and record
  the value it settles on: a side that should match does, and a side that is
  genuinely short is still reported unmatched with the length difference
- [ ] 8.5 Report an unmatched seam and keep it from stitching until the sides
  agree, and verify the report names the largest unmatched remainder
- [ ] 8.6 Re-run the mapping when a span is added, removed or invalidated, and
  verify the change report, the dropped-span report and the incomplete-side
  report
- [ ] 8.7 Add the UI: draw the spans of the first set, Enter, draw the spans of
  the second, with the pairing direction shown before the seam is created, and
  verify adding, ordering and removing a span afterwards
- [ ] 8.8 Verify a span that would put a set on a second pattern is refused with
  the reason, and that the engine payload is still one stitch group per seam

## 9. Copy options

- [ ] 9.1 Implement flip-in-place (horizontal, vertical, through two selected
  points) with the grain direction mirrored, and verify the sewings stay
  attached and the area is unchanged
- [ ] 9.2 Make internal lines copied by default with an outline-only option, and
  verify both paths and their reports
- [ ] 9.3 Implement copying the seams inside the selection by re-pointing them
  through the copy's uuid map, and verify a two-pattern double-layer copy, the
  crossing-seam report and one-undo rollback
- [ ] 9.4 Verify an instance copy and a mirror copy carry no seams, that the
  report says why, and that a plain copy of the same patterns still does

## 10. Interaction model and redo

- [x] 10.1 Add `ensure_edit_mode()` and have every tool that needs a mode
  activate it: the tool's `draw_cursor` for the toolbar path and the operator's
  `invoke` / `setup_state_machine` for every other path, and verify
  `ensure_edit_mode` is a no-op when the mode is already right
- [x] 10.2 Take the mode check out of the `poll` of the pen, add-vertex,
  add-spline-point, internal-line and sewing operators, so a tool is available
  wherever a project is being edited and can no longer fail silently
- [x] 10.3 Keep the selection when the mode changes and draw another mode's
  selected edges, vertices and sewings dimmed, so a selection made before a
  mode switch is still visible and still there when the mode comes back
  (each mode keeps its own selection list, and the drawing path now reads every
  mode's list: the active mode's selection is drawn in full colour, another
  mode's is the same colour at 0.35 alpha and one pixel thinner. The lookup the
  drawing path uses is tolerant of an entry whose element is gone, so a stale
  selection cannot fail a redraw, while the editing callers keep the strict
  lookup that reports a shifted identity. Checked headless by
  `.agents/scratch/probe_selection_modes.py`, 19 checks, 0 failures)
- [x] 10.4 Make the geometry commands act on the current selection (hover only
  decides what a click selects), starting with the first three commands, so a
  re-run finds its target again from the restored selection
  (`pattern_geometry.selected_edge_run` resolves the pattern and the edge indices
  from the selection, and reports what it found instead of guessing)
- [x] 10.5 Give the geometry commands semantic RNA parameters and a re-runnable
  `execute()` (modal and re-run paths on one code path, resolved values written
  back), and verify Blender's adjust-last-operation panel re-applies a division
  by count, a division by target length and a corner radius with a new value
  instead of applying the change twice
  (the division operator holds `mode` / `parts` / `distance` / `cuts` as RNA
  properties on one `execute`; count and target length were verified in a live
  session, a division left behind by the previous run is removed because Blender
  rolls the operator's own undo step back before re-running it. The corner
  radius is part of group 3)
- [x] 10.6 Recompute the seam remapping inside the command from the
  pre-operation edges (label first, geometry second) and verify a re-run drops
  and keeps exactly the same seams as the first run, with the same report
  (`_sewing_ends` reads the seams that reference a divided edge before the
  split, `_remap_sewing_ends` re-points them at the pieces afterwards, and the
  command ends by setting the pattern's `need_sewing_update` signal - it never
  touches a section itself, which is what leaves a re-run deterministic. Checked
  by the same scratch script: a seam on a divided edge keeps both endpoints
  where they were and lands on the piece that replaced its edge, and
  `tools/check_section_invariants.py` passes on the reloaded scene)
- [x] 10.7 Document the exceptions - the pens, the sewing tool, box select and
  the 3D pick - in the shipped reference, with the reason they have no redo
  pattern
  (`docs/agent-api.md`, "Deliberately not offered": the gesture tools are not
  calls at all - they have no entry point on the script surface - and that is
  the same reason the editor gives them no adjustable parameter, while a
  geometry command shows its numbers in Blender's own panel)
- [x] 10.8 A renderer found on a model object is checked against that object's
  identity before it is used, because Blender hands the temp data of a removed
  edge to the next edge added over it - a renderer inherited that way is bound
  to a dead identity and its lookup raises. A fan run crashed on exactly that in
  a windowed session, and `.agents/scratch/probe_renderer_binding.py` reproduces
  it headlessly with a stand-in that performs the same identity lookup
  (the GPU renderer cannot be built in a background session, which is why the
  earlier headless runs never reached the path)

## 11. Script surface and documentation

- [ ] 11.1 Expose the divide, corner, fan, curve-drag, cut, internal-line
  spacing, seam-span and copy-option calls through `qyapi`, and verify each
  round trip reports the same values the editor produces
- [ ] 11.2 Update `docs/agent-api.md` with the new calls, in English
- [ ] 11.3 Update the README feature table so the delivered commands stop being
  listed as missing, and so the pleat rows say they wait for the engine's
  internal-line angle support

## 13. Sewing, drawn and edited

- [x] 13.1 Draw a seam by dragging: the first half along one pattern's outline,
  then the second half along the pattern it joins, with snapping
  (`Qianyi/operators/_2d_add_sewing_free.py`, `Qianyi/model/sewing_geometry.py`
  and the tool beside it: a half is the run of the outline the pointer sweeps,
  pressed and released; the start snaps to the pattern's vertices and the ends of
  halves that are already there, and while the second half is drawn the place
  that makes it exactly as long as the first one is marked and snapped to. The
  first half waits in the project while the second is drawn, so the view can be
  moved between them; escape during a drag drops that drag, the tool's own escape
  drops the half that is waiting. Lengths are measured in millimetres and stored
  as fractions of the edge lengths. Checked by
  `.agents/scratch/probe_sewing_free.py` - 24 checks, and
  `.agents/scratch/probe_sewing_geometry.py` for the geometry layer)
- [x] 13.2 Edit a half: an end that grows or shrinks it, or the half itself
  sliding along the outline keeping its length, both with snapping
  (`Qianyi/operators/_2d_sewing_edit.py`: the press decides whether it took an
  end or the body; ends snap to vertices, other halves' ends and the opposite
  half's length; a sliding half snaps each end on its own. Every move is
  measured from the shape the drag started with, so dragging back and forth is
  exact. One drag is one undo step; a move that would leave no half, or one the
  linking run then refuses, is taken back. Checked by
  `.agents/scratch/probe_sewing_edit.py`)
- [x] 13.3 Flag a seam whose two halves cannot be paired, and hold its patterns
  out of the mesh and the simulation
  (`Qianyi/model/sewing_guard.py`: after every linking run each seam's two
  walks are counted - the numbers the stitch pairing needs to be equal - and a
  seam that fails is flagged (`Sewing.stitch_error`, drawn in red) together with
  the seams that share its pieces. Its patterns carry the reason, build no mesh
  and are refused by the simulation's own invalid-pattern check; fixing the seam
  graph clears it. Checked by `.agents/scratch/probe_sewing_guard.py`)
- [x] 13.4 Link the seam graph again when a seam is removed
  (`QianyiProject.remove_sewing` / `sewings_changed`, called from the delete
  operator, the script surface, a generator rebuild and the impacted-seam batch:
  the seams that are left are linked again and the guard runs, so a pattern held
  out of the mesh by a seam gets its mesh back as soon as that seam is gone)

## 12. Integration verification

- [ ] 12.1 Draft one skirt from scratch with the new tools (rectangle, circle
  waistband, target-length hem division, a rounded corner, a pivot fan at the
  hem, an internal line cut, spaced fold lines, a many-to-many seam to the
  waistband) and verify the outline is valid, the seams are matched, and a
  stepped simulation is finite
- [ ] 12.2 Undo the whole draft step by step and verify the project returns to
  its initial state with no leftover patterns, internal lines or seams
- [ ] 12.3 Verify a pattern built by these commands meshes and simulates with no
  engine error, using the existing scene-capture path
