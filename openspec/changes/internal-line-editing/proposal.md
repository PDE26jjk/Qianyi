## Why

An internal line is drawn geometry like the outline, and the mesh already treats
it that way: the engine meshes, sections and stitches internal lines today. The
interactive tools do not. Their pointer search only knew the outline, their
snapping answered in outline distances, and the sewing half measured its run
around an outline, so a seam made on an internal line could be created - by the
one-to-one tool, or by a script - but not drawn, edited, or given a point.

## What Changes

- A run of a chain is what the sewing tools measure: the outline, which is closed
  and may be wrapped, or one internal line, which is open unless it was drawn as
  a loop. On an open chain the run stays between the line's ends: an end dragged
  past the other turns the run round instead of laying it the long way round, and
  the stitching walk refuses a side that would have to leave the chain.
- The pointer's own chain is what the tools read: the pick pass draws the outline
  edges and every internal line's alike, so the free-sewing tool can start on
  either, the editing tool takes the half and its two ends there, and snapping
  offers the chain's own points and the ends of the halves made on that chain.
- The point tools work on an internal line: add-vertex splits the line's own
  piece (a new Sketch vertex, the outline untouched) and add-spline-point bends
  it, both from the edge the pointer is on.

## Capabilities

### New Capabilities

- `internal-line-editing`: runs on an outline or an internal line, the open-chain
  rules (no wrapping, the run turns round, the stitch walk stays inside the
  line), and the tools that read the pointer's own chain.

### Modified Capabilities

(none - this extends the same tools the editing toolkit describes)

## Impact

- Geometry: `Qianyi/model/sewing_geometry.py` (runs are read in the chain's own
  space; `run_of`, `run_place`, `run_travel`, `side_run`, `run_candidates`,
  `run_place_under`).
- Stitching: `Qianyi/model/sewing.py` (`calc_sewing_side_edges` walks an open
  chain without wrapping past its ends).
- Tools: `Qianyi/operators/_2d_add_sewing_free.py`,
  `_2d_sewing_edit.py`, `_2d_add_vertex.py`, `_2d_add_spline_point.py`,
  `_2d_operator_base.py`, their `workspacetools`, and the pick pass in
  `Qianyi/gizmos/temp_draw_manager.py`.
- Engine and the simulation payload: untouched - the engine's nearest-edge search
  is a flat point search the frontend decides what to feed, and its curve calls
  already take per-curve `is_loop` flags.
