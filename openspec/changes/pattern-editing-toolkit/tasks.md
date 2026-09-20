## 1. Shared curve rules and precision

- [ ] 1.1 Add the project constants for the fitting tolerance, the control
  point cap and the merge threshold (in code, documented in `LOCAL_DEV.md` only
  if a value turns out to be machine-specific) and state in the docstring why
  they are independent of a panel's granularity
- [ ] 1.2 Add the arc-length sampling and fitting helper: sample a curve by arc
  length, fit control points within the tolerance and the cap, return the
  closest fit with a flag when the tolerance was not reached, keep a straight
  piece straight and an exactly-representable piece as a Bezier
- [ ] 1.3 Add the merge helper: merge a produced point with an existing point
  closer than the threshold, and reduce a part count that would produce pieces
  shorter than it, reporting both
- [ ] 1.4 Verify a divided Bezier stays within the fitting tolerance of the
  original, that dividing it twice matches dividing it once within the same
  tolerance, that a divided straight edge is exactly straight, and that a cut
  point landing inside the merge threshold reuses the existing vertex

## 2. Edge division

- [ ] 2.1 Add the model-layer divide function for an edge or an edge chain
  (wrap over a whole outline), dividing by arc length with the fitting and merge
  rules of group 1
- [ ] 2.2 Add the target-length mode: distance plus cut count (default one,
  capped at what the selection holds), a point every distance along the arc
  length, the last piece absorbing the remainder, with the achieved lengths, the
  remainder and the cap in the report
- [ ] 2.3 Apply a division to every member of the instance chain and verify the
  members stay index-aligned
- [ ] 2.4 Add the operator and workspace tool for both modes, with live preview
  of the inserted points, and verify one undo step removes them

## 3. Corner tools

- [ ] 3.1 Implement the corner command with `ROUND`, `CHAMFER` and `CONCAVE`:
  tangent length from the interior angle, two points on the adjacent edges
  joined by an arc, a straight edge or the mirrored arc, with the corner
  material removed or added as the mode says
- [ ] 3.2 Implement the largest-fitting-radius refusal, naming the limit, and
  allow a corner whose neighbour is a curve by trimming that curve first
- [ ] 3.3 Make a multi-vertex run apply when the tangent lengths do not overlap
  and refuse with the vertex named when they do
- [ ] 3.4 Wire the radius to the drag and to the redo panel, and verify a re-run
  applies the new radius instead of adding a second corner treatment
- [ ] 3.5 Verify the outline is one closed loop after each mode and that a
  result crossing itself is refused with the crossing point

## 4. Pivot fan

- [ ] 4.1 Implement the fan: pivot and target on the outline, radius from the
  distance between them, the chord dividing the panel, the chosen half rotating
  rigidly about the pivot by an angle that starts at zero, the sector filled in
  between the radius and its rotated image, and the new arc edge from the target
  to its rotated image
- [ ] 4.2 Implement and report the added area, and refuse the cases in the spec
  (a point that is not on the outline, a chord crossing the outline, a result
  crossing itself)
- [ ] 4.3 Verify no internal line is created for either radius, that the
  stationary half is untouched, and that a seam on a moved edge follows the
  rotation
- [ ] 4.4 Wire the angle to the drag and the redo panel, and verify a re-run
  rebuilds from the pre-operation state with the new angle

## 5. Curve editing through points

- [ ] 5.1 Add the drag tool that fits the edge through the dragged position,
  keeping both ends attached to their neighbours
- [ ] 5.2 Verify no centre, radius or sweep is stored, that dragging a
  command-produced arc leaves a spline through the dragged points, and that the
  drag reports when the fit could not reach the tolerance

## 6. Rectangle and circle primitives

- [ ] 6.1 Add the rectangle component with its parameter schema and verify the
  placed outline area and the stable edge labels across a rebuild
- [ ] 6.2 Add the circle and annulus components and verify the hole is honoured
  by the mesh stage
- [ ] 6.3 Verify a placed primitive rebuilds in place with its sewings
  remapped, and that the rebuild report names anything it could not rebuild
- [ ] 6.4 Verify detaching a primitive yields an ordinary editable panel

## 7. Internal line tools

- [ ] 7.1 Implement the cut along an internal line that crosses the outline
  exactly twice, validating both resulting outlines before committing, and
  verify the two panels' areas sum to the original
- [ ] 7.2 Implement the refusals (no crossing, one crossing, three or more
  crossings, a closed line inside the panel) and verify each names its reason
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
  today's run: a panel, an edge index, a position range and a direction), and
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
- [ ] 8.8 Verify a span that would put a set on a second panel is refused with
  the reason, and that the engine payload is still one stitch group per seam

## 9. Copy options

- [ ] 9.1 Implement flip-in-place (horizontal, vertical, through two selected
  points) with the grain direction mirrored, and verify the sewings stay
  attached and the area is unchanged
- [ ] 9.2 Make internal lines copied by default with an outline-only option, and
  verify both paths and their reports
- [ ] 9.3 Implement copying the seams inside the selection by re-pointing them
  through the copy's uuid map, and verify a two-panel double-layer copy, the
  crossing-seam report and one-undo rollback
- [ ] 9.4 Verify an instance copy and a mirror copy carry no seams, that the
  report says why, and that a plain copy of the same panels still does

## 10. Interaction model and redo

- [x] 10.1 Add `ensure_edit_mode()` and have every tool that needs a mode
  activate it: the tool's `draw_cursor` for the toolbar path and the operator's
  `invoke` / `setup_state_machine` for every other path, and verify
  `ensure_edit_mode` is a no-op when the mode is already right
- [x] 10.2 Take the mode check out of the `poll` of the pen, add-vertex,
  add-spline-point, internal-line and sewing operators, so a tool is available
  wherever a project is being edited and can no longer fail silently
- [ ] 10.3 Keep the selection when the mode changes and draw another mode's
  selected edges, vertices and sewings dimmed, so a selection made before a
  mode switch is still visible and still there when the mode comes back
- [ ] 10.4 Make the geometry commands act on the current selection (hover only
  decides what a click selects), starting with the first three commands, so a
  re-run finds its target again from the restored selection
- [ ] 10.5 Give the geometry commands semantic RNA parameters and a re-runnable
  `execute()` (modal and re-run paths on one code path, resolved values written
  back), and verify Blender's adjust-last-operation panel re-applies a division
  by count, a division by target length and a corner radius with a new value
  instead of applying the change twice
- [ ] 10.6 Recompute the seam remapping inside the command from the
  pre-operation edges (label first, geometry second) and verify a re-run drops
  and keeps exactly the same seams as the first run, with the same report
- [ ] 10.7 Document the exceptions - the pens, the sewing tool, box select and
  the 3D pick - in the shipped reference, with the reason they have no redo
  panel

## 11. Script surface and documentation

- [ ] 11.1 Expose the divide, corner, fan, curve-drag, cut, internal-line
  spacing, seam-span and copy-option calls through `qyapi`, and verify each
  round trip reports the same values the editor produces
- [ ] 11.2 Update `docs/agent-api.md` with the new calls, in English
- [ ] 11.3 Update the README feature table so the delivered commands stop being
  listed as missing, and so the pleat rows say they wait for the engine's
  internal-line angle support

## 12. Integration verification

- [ ] 12.1 Draft one skirt from scratch with the new tools (rectangle, circle
  waistband, target-length hem division, a rounded corner, a pivot fan at the
  hem, an internal line cut, spaced fold lines, a many-to-many seam to the
  waistband) and verify the outline is valid, the seams are matched, and a
  stepped simulation is finite
- [ ] 12.2 Undo the whole draft step by step and verify the project returns to
  its initial state with no leftover panels, internal lines or seams
- [ ] 12.3 Verify a panel built by these commands meshes and simulates with no
  engine error, using the existing scene-capture path
