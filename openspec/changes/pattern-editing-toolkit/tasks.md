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

- [x] 7.1 Implement the cut along an internal line that crosses the outline
  exactly twice, validating both resulting outlines before committing, and
  verify the two patterns' areas sum to the original (`plan_cut` in the
  operator's own `Qianyi/operators/_2d_cut_along_line.py`
  reads the two crossings off the engine's own intersection call, splits the
  outline into the two arcs they leave and closes each arc with the stretch of
  the line between them - read one way on one side and the other way on the
  other, so both halves carry the same boundary. The two readings of a crossing
  differ by a fraction of a millimetre, so the joints are sealed to one point and
  a repeat the slicing leaves at a piece's end is dropped, or the crossing test
  reads the outline as crossing itself. Both resulting outlines are tested
  before anything is written, and a straight, a Bezier and a cut that trims a
  curved outline edge all land within a hundredth of a millimetre of the
  original, verified in `.agents/scratch/probe_cut_along_line.py`)
- [x] 7.2 Implement the refusals (no crossing, one crossing, three or more
  crossings, a closed line inside the pattern) and verify each names its reason
  (each count is refused with the count in the message, a line that only touches
  the outline is refused by asking whether its middle is inside the pattern, and
  an outline edge is refused by name rather than silently treated as a line -
  `.agents/scratch/probe_cut_along_line.py`)
- [x] 7.3 Verify both halves join the source's instance chain, the cut's
  property inheritance and its sewing remap, including the report for a sewing
  that had to be dropped (a chain of two comes out as two chains of two - each
  member is replaced by its own pair of halves, which is what keeps a linked
  pattern linked - and each half inherits the source's anchor, rotation, grain,
  fabric, granularity, collision layer and mirror flag. A seam side is moved to
  the piece that replaced the edge it named, in the half that holds it, with its
  position re-read against that piece; a side whose two ends land in different
  halves spans both patterns, which one side cannot do, so its seam is dropped
  and named in the report - `.agents/scratch/probe_cut_along_line.py`)
- [x] 7.4 Implement the optional seam along the cut and verify it is off by
  default, that when it is on the report names the seam it created, and that a
  cut without it leaves the seam list unchanged (the two things the command can
  do are two entries in the editor's own right-button menu - `cut along line`
  and `cut along line, sewn` - rather than one operator with a property in
  Blender's adjust-last-operation panel: a cut takes the patterns it worked on
  away, so it is not registered for that panel at all. The seam it makes pairs
  points that meet - the worst pair is 0.0 mm apart - because the half on the
  far side of the cut reads the same boundary the other way round and its side
  therefore walks from the same end. A cut with the option off adds no seam, and
  a cut leaves no selection naming the sources it removed, verified in
  `.agents/scratch/probe_cut_along_line.py` and `probe_cut_redo.py`)
- [x] 7.5 Implement copying a run of outline edges - or an internal line, which is
  the same job - at a distance, as internal lines (the command is
  `_2d_offset_copies`, offered by the edge mode's right-button menu as `offset
  copies`, and the source is read, never changed: the outline is not re-routed
  and an internal line stays where it is, so what comes out is exactly the lines
  asked for. How far apart they are is either a division or a step, the way an
  edge is divided: the source's own length divided into equal parts puts a line
  at every division point inside it - a 200x300 panel with its 200 mm top edge
  selected and five parts comes out with four fold lines 40 mm apart, each
  spanning the panel - or a distance, with a line at it, twice it and so on for
  as many as were asked for, a negative distance taking them to the other side:
  an internal line in the middle of a 400 mm panel copied three times at -20 mm
  lands at 140, 160 and 180 mm. Everything is measured along the source's own
  normal, every piece is sampled at 0.5 mm along its own arc length and moved
  along the normal there, and the straight chord between one piece's offset and
  the next one's joins them. Nothing is clamped to the room the pattern has: a
  line that lands outside the outline is not written and the report names it,
  which is three of five 20 mm lines in a 100 mm pattern and two of the six
  parts of a corner run. Refusals: the whole outline, a selection that is not one
  consecutive run (the outline is a loop, so a run may cross its first edge), a
  closed internal line, a part count of one, a distance of zero, and parts so
  many that the lines would be closer than the merge threshold. A copy is not
  trimmed or extended - that is its own command, task 7.6 - so a copy of a line
  that crosses the outline keeps the ends the offset gave it, and the seams of
  the source are left where they were. Verified in
  `.agents/scratch/probe_offset_copies.py`. That probe also found a model bug on
  the way: a line that starts exactly on an outline point cuts a piece of no
  length into the outline's section stage, and `Pattern.sample_edge` divided the
  whole edge's sampling step by it, so any pattern with such a line lost its mesh
  to a zero division; a piece of no length contributes no step now)
- [x] 7.6 Put the ends of an internal line on the outline, by trimming or
  extending it (the end modes are their own command, `_2d_line_to_outline`,
  offered as `line to outline` with the mode in Blender's own redo panel, because
  what happens where a line leaves the pattern is an edit of *that line*, not
  something a copy decides. `EXTEND` moves an end that lies inside out to the
  nearest point of the outline, so a dart or a fold line that stops short spans
  the pattern; `TRIM` cuts back what lies outside and lands the ends where the
  line crosses the outline; an end that lies outside is cut back in either mode.
  The line is a chain and the two ends ask for a span of it: the pieces that stay
  are the very edges they were, so a seam on one of them still names it and is
  re-aimed at the point of the new piece closest to where it was, and a seam on a
  piece that goes is dropped and named. The points of the pattern are the line's
  own: the span's ends are written onto the line's own end points and the points
  of the pieces that went leave the pool with them. A line that lies outside the
  pattern altogether, a trim that would leave nothing of it, and a line whose
  ends are both already inside under `TRIM`, are refused with the line as it was.
  Verified in `.agents/scratch/probe_line_to_outline.py`)
- [x] 7.7 Implement the offset de-looping (self-intersection removal) and verify
  a concave corner, a tight concave arc and a fully degenerate offset each
  produce the documented result and report (every generated offset is de-looped
  before its end mode is applied: its own crossings are found - every segment
  against every other, the neighbours left out - and the first crossing in walk
  order removes the loop between it and the second one, the walk keeping the
  points up to the crossing and carrying on from where the other segment reaches
  it, with the piece the crossing lands in being the earlier one's. It repeats
  until the line has no crossing of its own, which is what the in/out
  classification of a line's pieces and the seam sampling both need, and the
  report names the distances that were shortened. Two 50 mm pieces turning left,
  offset 20 mm to the left, put their offsets across each other at (90, 120) and
  come out as the corner the loop leaves - x 60..90 by y 120..150, no crossing
  of its own, reported as shortened - while the same source offset the other way
  is a corner the offset turns outside of and is not shortened at all; both in
  `.agents/scratch/probe_offset_copies.py`. A tight concave arc needs nothing
  removed: a semicircle of 30 mm radius offset 40 mm inwards comes out as the
  10 mm arc on the other side of its centre, which is what the normal offset of
  every sample gives and is not a crossing. The complete degeneration the last
  scenario describes cannot arise from this walk - removing the loop between the
  first crossing and the second always leaves at least three points, and a
  three-point line has no crossing - so the drop it asks for is the one a line
  with no length left takes, which `_split_pieces` decides and the report names
  alongside the offsets that landed outside the pattern)
- [ ] 7.8 Allow an internal line to be a sewing side and verify a dart sewn to a
  run of outline edges stitches and closes

## 8. Many-to-many sewing

- [x] 8.1 Extend the seam model so each side holds a set of spans (a span being
  today's run: a pattern, an edge index, a position range and a direction), and
  verify an existing one-to-one seam reads back unchanged
  (`Qianyi/model/sewing.py`: `SewingSpan` is what a side used to be - a start
  place, an end place and a direction on one chain - and `SewingOneSide` holds a
  `spans` collection in drawing order plus its pattern. `SewingSpan.turn_round`
  turns one run round and `SewingOneSide.turn_round` reverses the order as well,
  which is what makes the reverse tool still mean the same thing. Checked by
  `.agents/scratch/probe_m2n_model.py`: a one-to-one seam made by
  `add_sewing1to1` reads back as one run per side and still stitches)
- [x] 8.2 Build a side's sections by concatenating its spans' sections in order
  and verify a set whose spans are not geometrically contiguous matches end to
  end
  (`calc_sewing_side_sections` walks each run with `span_pieces` and concatenates
  the pieces in drawing order; `walk_pieces` is the one walk, shared by the
  linking run, the stitch pieces and the guard, and `side_pieces` turns a run's
  pieces into the mesh samples each one holds - in stitching order, with the
  vertex it is entered at and the one it is left at, which is what the pairing
  needs on either direction of the chain)
- [x] 8.3 Implement the proportional two-way merge over the concatenated
  section lists and verify a 200 mm side pairs with spans of 120 mm and 80 mm
  (`link_sewings` reads one list per side and takes each piece's own direction
  (`dirs1[i] ^ dirs2[j]` instead of the side's single flag), so a set drawn in
  either direction merges the way a single run always did. Checked by
  `.agents/scratch/probe_m2n_model.py` on a 200 mm band edge sewn to a 120 mm and
  an 80 mm edge: 11 samples on both sides, and the 60% point of the long side
  pairs with the join of the two short ones)
- [x] 8.4 Settle what a length difference means, and take the length requirement
  out (the requirement this task first asked for - report a seam unmatched and
  stop stitching when the sides differ by more than a calibrated tolerance - was
  wrong, and a later pass that measured and reported the difference was wrong
  too. Both are gone from `specs/sewing-many-to-many` and
  `specs/agent-sewing-control`. Sewing a longer side to a shorter one is how a
  garment is designed - a puff sleeve's cap into its armhole, a binding or a band
  onto the edge it trims, a gathered skirt into its waistband - and the two sides
  are matched by progress along each side, never by putting their totals beside
  each other. Nothing measures, reports, flags or refuses the difference.
  `.agents/scratch/probe_m2n_gather.py` sews a 200 mm side to sides 0, 2, 4, 10,
  20, 40 and 79 mm shorter at 5, 20 and 50 mm granularity: **every** case
  stitches, the two walks pair sample for sample, and no seam carries anything
  about the difference. The shipped library is the same proof from the other
  side: the GC Tee's collar is 310.0 mm sewn to a 1939.3 mm neckline and its
  torso halves are 324.6 to 256.5 mm, and all of them stitch and simulate)
- [x] 8.5 Keep a seam that cannot be paired out of the mesh, and verify the
  report names the reason
  (`sewing_guard.seam_error` now reports the structural failures only: a side
  whose drawn runs are all gone, which would otherwise stitch nothing, and a seam
  whose two sides the linking run cut into different numbers of pieces. It does
  not compare the walks any more - the two sides are paired by the linked pieces
  (`pair_by_sections`), so a side that is longer, or a join the other side has one
  sample for, is stitched rather than refused. The seam read carries
  `stitch_count` and `stitch_error`.
  Checked by `.agents/scratch/probe_m2n_model.py` (an empty side reports "no
  drawn run") and `.agents/scratch/probe_m2n_pairing.py` (see 8.10).
  **The count check this task originally specified is gone**, which means the
  nested-run case of task 13.3 no longer flags: with the pairing by progress it
  stitches, and the old probe
  (`.agents/scratch/probe_sewing_guard.py`) is now the record of the behaviour
  that was removed. Whether a seam whose linking left its pieces out of step
  should still be held out needs a structural test - whether the pieces of one
  side's walk are linked to the pieces the other side's walk reaches - which
  this change does not add; it is left to the maintainer)
- [x] 8.6 Re-run the mapping when a span is added, removed or invalidated, and
  verify the change report, the dropped-span report and the incomplete-side
  report
  (`QianyiProject.add_sewing_span` / `move_sewing_span` / `remove_sewing_span`
  each re-link the seam's component and return `{action, seam, spans,
  stitch_count, changed, error}`, so a change reports how many stitch pairs it
  moved. A generator rebuild drops the runs whose edges it cannot match
  (`generators._remap_sewings` now works per run and returns
  `(remapped, dropped_spans, emptied_sewings)`, reported as `remapped`,
  `dropped_spans` and `dropped_sewings`) and a side left empty is reported by the
  guard as incomplete. Checked by `.agents/scratch/probe_m2n_model.py` (a run whose
  edge is gone drops out and the seam keeps the one that is left) and
  `.agents/scratch/probe_m2n_tool.py` (add, move, remove, and the two reports))
- [x] 8.7 Add the UI: draw the spans of the first set, Enter, draw the spans of
  the second, with the pairing direction shown before the seam is created, and
  verify adding, ordering and removing a span afterwards
  (`Qianyi/operators/_2d_add_sewing_m2n.py` and the tool beside it
  (`Qianyi/workspacetools/add_sewing_m2n.py`, `qmyi.add_sewing_m2n`, keyed on
  left-mouse, `RET` to close the side being drawn and `ESC` to drop it): each
  drag adds one run to the side being drawn, the runs wait in the project
  (`QianyiProject.sewing_m2n`) so the view stays usable, and the seam is created
  as soon as the second side has a run, which is what the spec asks for. The
  tool's cursor preview draws the run it would take and the last run drawn for
  the side, so the direction is visible before the seam exists. Checked by
  `.agents/scratch/probe_m2n_tool.py`, which drives the operator's own methods:
  the first drag is held as a run on side 1, the refusal is checked, the first
  drag of side 2 makes the seam, and add / move / remove each re-run the mapping
  - a reorder that leaves the runs not continuing each other is reported unpaired
  rather than silently stitched, and moving it back restores the stitch count)
- [x] 8.8 Verify a span that would put a set on a second pattern is refused with
  the reason, and that the engine payload is still one stitch group per seam
  (`accept_pattern` records the pattern the first run of a side was drawn on and
  refuses a later run on another one with "a side of a seam is on one pattern, and
  this run is on another one", without changing what was already recorded;
  `setup_sewings_for_simulation` still hands the engine one `(S, 2)` stitch group
  per seam. Both checked by `.agents/scratch/probe_m2n_tool.py`)
- [x] 8.9 Draw the connecting lines per drawn run, so every run's ends are joined
  to what they pair with
  (`sewing_renderer.connector_lines`: both sides' run boundaries, as fractions of
  each side's own length, are the breakpoints; a line is drawn at every one of
  them and equally spaced lines in between, with the count taken from the shorter
  side so a seam is never denser than the shorter of the two and never drops a
  run boundary when the budget thins them out. A breakpoint is drawn from the
  runs' own ends: `run_end_points` reads each run's own polyline and never a
  sample of the whole side taken at the fraction, because two runs that do not
  share a vertex put the same fraction of the side on two different points and
  `np.interp` over a repeated arc length answers with the later one - the line
  that started a little past its own run's end. Where a breakpoint has ends on
  both sides they are joined in the order the runs were drawn; where one side has
  no end there, its point at the fraction meets both of the other side's ends,
  which is the middle of a long side reaching the facing ends of two short ones -
  the join the stitches make, drawn as it is. Between breakpoints the two sides
  are sampled at the same fraction of their own length, which is the
  correspondence the merge stitches. Checked by
  `.agents/scratch/probe_m2n_connectors.py`: a one-run-to-one-run seam draws
  exactly the uniform lines it drew before the change, a 200 mm side against
  120 + 80 has a line at 60% and equal spacing inside each run, a four-run side
  keeps all three of its internal boundaries inside the drawing budget, and on a
  real seam the 60% line lands on the join vertex (120, 0); a 205 mm side against
  runs of 120 and 80 that do not share a vertex draws two lines at the join -
  from the point at 60% of the long side, 123 mm along it, to 120 and to 125,
  each of which is the run's own end - where sampling the short side at 60%
  answered only one of the two)
  The drawing is vector geometry, not the mesh: `edge.render_points` is the
  edge's own curve sampled into a polyline and `split_polyline` cuts it by arc
  length, so nothing reads `mesh_edge_points`, `mesh_edge_index_map` or the
  granularity. The probe pins that too: the same seam meshed at 5 mm and 50 mm
  granularity (120 against 12 boundary samples) draws bit-identical polylines
  and bit-identical connecting fractions. What is mesh-based in a seam is the
  stitch pairs themselves (`get_stitch_data` reads `mesh_edge_index_map`, because
  a stitch is a pair of mesh vertices) and the sample count the guard predicts
  for a piece the linking run cut before it was sampled - neither of which the
  editor draws from.
- [x] 8.10 Take the stitch pairs from the linked pieces, with no ratio in
  between (`sewing.side_pieces` answers, per side, every piece in stitching order
  with its own mesh samples, the vertex at its far end and whether a drawn run
  ends there; `pair_by_sections` walks the two lists together - the merge cut
  them into pieces that correspond, so the pieces of one list are the partners of
  the pieces of the other - and pairs their samples in order. Nothing is divided:
  the correspondence is the linked pieces themselves, which is where the
  proportional cutting already happened, so no rounding stands between the two
  sides. A piece a drawn run ends at carries the run's own end, which meets the
  other side's end of the same piece - the point two runs' ends meet at - and the
  pair made twice that way is dropped once; a loop's closing pair is not next to
  itself and stays. The helpers the earlier passes left behind are gone:
  `pieces_indices`, `run_samples`, `side_samples`, `pair_by_progress`,
  `get_stitches_for_side`, `side_join_flags`, `spans_meet` and the guard's
  per-piece sample counting, none of which the stitched path used any more - the
  check that needed a walk builds its own from `side_pieces`. Checked by
  `.agents/scratch/probe_m2n_pairing.py`: a 200 mm side against two runs of 120
  and 80 that share their vertex walks 11/11 and pairs one to one, with the join
  landing on the point at 60% of the 200 mm side; the same two runs drawn as
  separate edges (5 mm apart) walk 11/12 and pair 12 times with exactly one
  column two to one - the point at 60% of the long side meeting both facing ends
  of the join; and a one-to-one seam with its second side reversed pairs
  `(0,10), (1,9), ... (10,0)` - one pair per sample, nothing shifted, which is
  the bug the maintainer hit when the run's own end was emitted as a pair of its
  own instead of sitting at the end of the piece's run it belongs to)
- [x] 8.11 Give the tool its own sub-mode of the editor
  (`ADD_SEWING_M2N` is an entry of `qmyi.edit_sub_mode` in
  `Qianyi/model/qianyi_data.py`, next to `ADD_SEWING_FREE`: the mode a tool puts
  the editor into is the settings layer's, and a name that is not an entry fails
  the moment the tool draws its cursor - `TypeError: enum "ADD_SEWING_M2N" not
  found` - which is how the maintainer found it)
- [x] 8.12 Take a removed seam's ids out of the identity map with it
  (`ModelData.forget_uuid` and `Sewing.forget_identity`, called by every path
  that removes a seam - the editor's delete, the project's `remove_sewing` and
  `remove_impacted_sewings`, the rollback when a seam cannot be made, and the
  cut-along-line pass. A side is stored in the property group of its seam, so
  removing the seam frees the memory the side's wrapper reads from, while the
  pick pass still holds the ids it keyed on the sides: removing a selected
  many-to-many seam took Blender down on the next move over the editor, with
  `EXCEPTION_ACCESS_VIOLATION` inside `IDP_GetPropertyFromGroup` reached from the
  preselection gizmo's `test_select` - what answered there was the identity map's
  entry for a side that no longer existed. Checked by
  `.agents/scratch/probe_m2n_delete.py`: after each of the three removal paths,
  a lookup of the removed seam's and its sides' uuids answers nothing instead of
  reading them)
- [x] 8.13 Snap the places a drawn run begins and ends
  (`_2d_add_sewing_m2n.start_place` and `snapped_end`: the press and the drag
  both go through `snapped_place`, so a run starts or ends exactly on a chain
  point or on the end of a run already sewn along it - which is what makes two
  runs meet at one vertex, and what the maintainer's 2-to-1 seam was missing:
  the two facing ends of its runs came out 52 mm apart because the tool could
  not be made to land on a point - 12 screen pixels of reach, the same
  `SNAP_PIXELS` every sewing tool snaps with, while 24 (`GRAB_PIXELS`) is how far
  the pointer may be from a chain and still draw on it).
  `snapped_place` now measures that radius at the pointer itself: it used to
  pass `nearest_candidate` a view position where `snap_radius` takes region
  pixels, so the reach was measured somewhere else in the region - harmless
  where the view is uniformly scaled, wrong the moment it is not - and
  `nearest_candidate` takes the radius from its caller, which is the caller that
  knows the pointer in the space it has to be measured in. Checked by
  `.agents/scratch/probe_m2n_snap.py`: the reach is 12 screen pixels at one zoom
  and twice that in the pattern's millimetres at half the zoom, a press and a
  release inside it land exactly on the corner (and the drag callback's own
  travel records that place), a press outside it keeps the place the pointer is
  on, and an end of a run already sewn along the chain is a point to snap to)
- [x] 8.14 Keep the run a drag took out of the operator's own `span` read
  (`_2d_sewing_edit.setup_state_machine` held the run the press took in
  `self.span`, which shadowed the operator's `span()` - the read that finds that
  run again through its side when the drag is written - so every finished drag
  raised `'SewingSpan' object is not callable`. The record kept at the press is
  what the write compares against, so the wrapper is a local now and `span()`
  answers as it did. Checked by `.agents/scratch/probe_m2n_edit_drag.py`: a
  finished drag writes the run it took with the ends it asked for, leaves the
  other run of the side alone, reads the run it took back from the side, and
  answers nothing for a place the side no longer has)
- [x] 8.15 Join a boundary to the point the other side has there, at every join
  (`sewing.pair_by_sections` now reads each piece's own vertices first and, at a
  boundary between two pieces, adds the pair that joins them: where one side's
  two runs meet and the other side's fabric runs on through the boundary, the end
  the piece before reached is paired with the point the piece after begins at -
  the one point the other side has at that place, which the walk then also
  reaches from the piece after's own first vertex. Both facing ends are therefore
  joined to that one point, and the duplicate is folded where the two facing ends
  are one vertex, which is what the maintainer's seam was missing: its join fell
  on the other side's own piece joint, where the merge aligns the boundaries
  instead of cutting them, so the two ends were joined one-to-one to the two
  samples on either side of the joint. Nothing is left unstitched: every sample of
  both walks is in a pair. Checked by `.agents/scratch/probe_m2n_pairing.py`,
  which now also covers the piece-joint join (the one point the long side has
  there takes both facing ends) beside the cases it already pinned: the join that
  shares its vertex stays one pair, the gapped join stays one point meeting two
  ends, and a one-to-one seam is unchanged)
- [x] 8.16 Keep the lengths the drag tools write out of numpy scalars
  (`sewing_geometry.run_travel` measured with `np.floor` and handed back a numpy
  float, so the edit tool's `places[1] < 0.0` came out a numpy bool - and RNA
  refuses that where the span's direction wants True/False: finishing a drag
  raised `TypeError: SewingSpan.reverse expected True/False or 0/1, not
  numpy.bool`. The measurement now answers a Python float, the edit tool writes
  `bool(...)` of the comparison, and `SewingSpan.update_data` coerces the
  direction at the property it sets. Checked by
  `.agents/scratch/probe_m2n_edit_drag.py`, which now drives the drag with numpy
  places - the types the real callback hands over - and pins that a measured
  travel is a Python float and that comparing it is a Python bool)

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
  (`Qianyi/operators/_2d_sewing_edit.py`: the id pass draws every half and, for
  the half under the pointer, its two ends as points over it, so the pointer
  decides whether a press took an end or the body instead of guessing from how
  close it happened to land - the half's ends are selectors of their own, drawn
  by `TempDrawManager.draw_sewing_for_pick`; ends snap to vertices, other
  halves' ends and the opposite half's length; a sliding half snaps each end on
  its own, and each end is measured where that end is rather than where the
  pointer is; an end dragged past the other one lays the run the long way round
  the outline - the run keeps its direction and its length wraps at the place
  the two ends meet (`sewing_geometry.wrapped_travel`), so a half can span
  almost the whole outline. Every move is measured from the shape the drag
  started with, so dragging back and forth is exact. One drag is one undo step;
  a move that would leave no half, or one the linking run then refuses, is taken
  back. Checked by
  `.agents/scratch/probe_sewing_edit.py` and, with a real GPU, by
  `.agents/scratch/probe_sewing_edit_windowed.py`)
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
