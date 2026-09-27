## 1. A run of a chain

- [x] 1.1 Read a sewing half in its chain's own space: the outline, or the
  internal line it was made on (`sewing_geometry.run_of`, `side_run`)
- [x] 1.2 Give a chain's two kinds their own rules: a closed one wraps and a run
  may span almost all of it, an open one keeps the run between its ends and turns
  it round (`run_place`, `run_step`, `run_travel`, `run_from`)
- [x] 1.3 Offer the chain's own points and the ends of the halves made on that
  chain to snapping (`run_candidates`, `run_nearest_distance`)
- [x] 1.4 Walk a side of a seam without wrapping past an open chain's ends, and
  refuse the ones that would have to (`model/sewing.py:calc_sewing_side_edges`)

## 2. The sewing tools

- [x] 2.1 Find the pointer's place on either chain - the outline through the
  project's search, an internal line through its own pieces - and answer with the
  pattern that draws it (`sewing_geometry.run_place_under`)
- [x] 2.2 Draw a new half along whichever chain the pointer is on, and keep which
  chain the waiting half was drawn on between the two drags
  (`operators/_2d_add_sewing_free.py`, its tool)
- [x] 2.3 Edit a half on an internal line: its two ends are selectors, its run is
  measured in the line, and the pointer has to be on that line
  (`operators/_2d_sewing_edit.py`, its tool, the id pass)
- [x] 2.4 Draw the seam under the pointer again, thicker, so what a click would
  take is visible before the click: the pick pass names the half now, which is
  what makes the hover knowable at all, and the highlight is the seam's own
  renderer drawing both halves (`gizmos/temp_draw_manager.py:draw_hover`;
  checked in a window by `.agents/scratch/probe_sewing_edit_windowed.py`)

## 3. The point tools

- [x] 3.1 Read the edge the finder answers with, which may be a piece of an
  internal line, and the click's fraction along it
- [x] 3.2 Split the chain the edge came from rather than the outline
  (`model/pattern.py:chain_of_edge`; `operators/_2d_add_vertex.py`)
- [x] 3.3 Write a control point into the chain the edge came from
  (`operators/_2d_add_spline_point.py`)

## 4. The edge finder carries internal lines

- [x] 4.1 Feed the finder one group per chain - each pattern's outline, then each
  of its internal lines - with the pattern's own matrix, and repeat an open
  chain's last point so the edge the engine closes the group with is a point
  rather than a line across the gap (`Pattern.edge_finder_groups`,
  `QianyiProject.update_edge_finder`)
- [x] 4.2 Build the session data a snapshot is made of rather than snapshot an
  empty one: the samples are session data, so a pattern a file was opened with has
  none until it is asked, and the snapshot's own layout is taken from the groups
  that went in so the two cannot disagree (`Pattern.edge_finder_groups`,
  `QianyiProject.update_edge_finder`)
- [x] 4.3 Take a snap's index back to the chain, the edge and the fraction in the
  chain's own space, and tell a stale snapshot by the chains' sample counts
  (`find_nearest_point_on_edge`, `get_nearest_point_data`,
  `chain_sample_counts`, `live_edge_finder_layout`)
- [x] 4.4 Let the point tools snap a whole radius off a chain rather than only on
  it, and draw the preview point from what the finder answered - for an internal
  line as well as for the outline (`gizmos/temp_draw_manager.py`)
- [x] 4.5 Keep the sewing tools on their own search: their outline place comes
  from the finder, and an internal line is measured from its own pieces, so a tool
  that draws or edits a half does not depend on the finder's snapshot at all
  (`sewing_geometry.run_place_under`)
- [x] 4.6 Leave a chain the sampler answered nothing for out of the snapshot
  instead of raising: one unsampled chain used to take the whole finder, and
  every tool that reads it, down with it (`chain_sample_counts`,
  `update_edge_finder`, `live_edge_finder_layout`)
- [x] 4.7 Keep the snapshot current from the point tools' own cursor - every
  frame, not only when the mode changes - so an undo or a reload that drops it
  does not leave the tool with no preview and no place to click
  (`workspacetools/add_vertex.py`, `workspacetools/add_spline_point.py`)

## 5. What a new point hands to the next tool

- [x] 5.1 Clear the point and the edge selection, select the point that was just
  added, and make the member the click was made on the active pattern, so a move
  that follows immediately acts on it with that member's own transform - a
  mirrored instance carries the point in a space of its own
  (`operators/_2d_add_vertex.py`, `operators/_2d_add_spline_point.py`)

## 6. Verification

- [x] 6.1 `.agents/scratch/probe_sewing_edit.py`: a half on an internal line -
  its ends as selectors, an end grown along the line, an end dragged past the
  other one turning the run round, a pointer that leaves the line, and the
  outline cases unchanged
- [x] 6.2 `.agents/scratch/probe_internal_points.py`: a click a millimetre off an
  internal line answering with that line, a spline point on it, a vertex
  splitting it with the outline untouched, the same tools still working on the
  outline, what each new point leaves selected, and the tool's cursor rebuilding
  a snapshot that was dropped
- [x] 6.3 `.agents/scratch/probe_edge_finder_robust.py`: one chain with no
  samples leaving the snapshot readable for the chains that have them, and a
  pattern with no session data at all (a file just opened) still being put into
  the snapshot
- [x] 6.4 The sewing and point probes, `tools/probe_agent_api.py`,
  `tools/test_divide_edge.py` and `tools/check_section_invariants.py` (which
  includes a sewing on an internal line) all pass
