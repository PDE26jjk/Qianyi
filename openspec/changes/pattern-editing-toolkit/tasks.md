## 1. Edge division

- [ ] 1.1 Add the model-layer divide function for an edge or an edge chain
  (equal count), splitting curves with the existing split helpers instead of
  resampling, and verify a twice-divided Bezier keeps its shape within the
  sampling tolerance
- [ ] 1.2 Add the target-length mode with the remainder report and the refusal
  when fewer than two parts fit, and verify the reported lengths and the
  refusal message
- [ ] 1.3 Apply a division to every member of the instance chain and verify the
  members stay index-aligned
- [ ] 1.4 Add the operator and workspace tool for both modes, with live preview
  of the inserted points, and verify one undo step removes them

## 2. Arc edges, fillet and extend

- [ ] 2.1 Add arc parameters to an edge (three-point and centre/radius/sweep
  forms) realised through the library's `Arc` -> Bezier lowering, and verify
  the sampled points stay within 0.05 mm of the requested circle
- [ ] 2.2 Add arc drawing and editing (change radius and sweep through the
  parameters, drag points, keep the ends attached), verify the neighbours stay
  connected, and verify a handle drag clears the arc parameters
- [ ] 2.3 Implement the vertex fillet with the largest-fitting-radius refusal,
  and verify the resulting outline is one closed loop and the area decreases by
  the corner area
- [ ] 2.4 Implement the edge extension by a tangent arc with an explicit sweep
  override, and verify the extension is a new edge and the other edges are
  unchanged
- [ ] 2.5 Verify each of the three commands is refused with the crossing point
  when interactive self-intersection checking is on and the result would cross
- [ ] 2.6 Verify the mesh stage, the sewing sampling and the engine payload see
  an arc as points only, by meshing and sewing a panel that uses an arc

## 3. Rectangle and circle primitives

- [ ] 3.1 Add the rectangle component with its parameter schema and verify the
  placed outline area and the stable edge labels across a rebuild
- [ ] 3.2 Add the circle and annulus components and verify the hole is honoured
  by the mesh stage
- [ ] 3.3 Verify a placed primitive rebuilds in place with its sewings
  remapped, and that the rebuild report names anything it could not rebuild
- [ ] 3.4 Verify detaching a primitive yields an ordinary editable panel

## 4. Internal line tools

- [ ] 4.1 Implement the cut along an internal line, validating both resulting
  outlines before committing, and verify the two panels' areas sum to the
  original
- [ ] 4.2 Verify the cut's property inheritance and its sewing remap, including
  the report for a sewing that had to be dropped
- [ ] 4.3 Implement converting a run of outline edges into an internal line
  (chord re-route), with the whole-outline and chord-crossing refusals
- [ ] 4.4 Implement repeated internal lines at a signed distance with clipping
  and the report for dropped offsets
- [ ] 4.5 Allow an internal line to be a sewing side and verify a dart sewn to
  a run of outline edges stitches and closes

## 5. Pleat commands

- [ ] 5.1 Implement knife and box pleats on a panel with count, depth and
  direction, and verify the reported take-up and resulting circumference
- [ ] 5.2 Implement sewn pleats that create the holding seams, and verify the
  seams are ordinary seams (list, colour, delete)
- [ ] 5.3 Implement the preview and the validations (depth over available
  width, fold spacing under the mesh tolerance, invalid outline, generated
  panel), and verify each refusal names its limit
- [ ] 5.4 Verify one undo removes the fold lines, the seams and the vertices
  the command created

## 6. Many-to-many sewing

- [ ] 6.1 Extend the seam model to two sides with ordered span lists (span =
  edge run plus two positions, on any panel) and verify an existing one-to-one
  seam reads back unchanged
- [ ] 6.2 Implement the proportional section mapping across the two sides with
  the documented tolerance and the unmatched-remainder report, and verify a
  200 mm side pairs end to end with 120 mm and 80 mm spans
- [ ] 6.3 Decompose the stitches into one engine stitch group per panel pair
  and verify a three-panel junction seam produces two groups and one seam in
  the project
- [ ] 6.4 Report an unmatched seam and keep it from stitching until the sides
  agree, and verify the length difference is named
- [ ] 6.5 Re-run the mapping when a span is added, removed or invalidated, and
  verify the change report and the incomplete-side report
- [ ] 6.6 Add the UI for adding, ordering and removing spans, and verify the
  seam preview shows the pairing direction

## 7. Copy options

- [ ] 7.1 Implement flip-in-place (horizontal, vertical, through two selected
  points) with the grain direction mirrored, and verify the sewings stay
  attached and the area is unchanged
- [ ] 7.2 Make internal lines copied by default with an outline-only option,
  and verify both paths and their reports
- [ ] 7.3 Implement copying the seams inside the selection by re-pointing them
  through the copy's uuid map, and verify a two-panel double-layer copy, the
  crossing-seam report and one-undo rollback

## 8. Script surface and documentation

- [ ] 8.1 Expose the divide, arc, fillet, extend, cut, internal-line spacing,
  pleat, seam-span and copy-option calls through `qyapi`, and verify each
  round trip reports the same values the editor produces
- [ ] 8.2 Update `docs/agent-api.md` with the new calls, in English
- [ ] 8.3 Update the README feature table so the delivered commands stop being
  listed as missing

## 9. Integration verification

- [ ] 9.1 Draft one skirt from scratch with the new tools (rectangle, circle
  waistband, target-length hem division, fillet, internal line cut, spaced fold
  lines, sewn pleats, a many-to-many seam to the waistband) and verify the
  outline is valid, the seams are matched, and a stepped simulation is finite
- [ ] 9.2 Undo the whole draft step by step and verify the project returns to
  its initial state with no leftover panels, internal lines or seams
- [ ] 9.3 Verify a panel built by these commands meshes and simulates with no
  engine error, using the existing scene-capture path
