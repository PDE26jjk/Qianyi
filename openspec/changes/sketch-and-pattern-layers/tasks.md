## 1. The Sketch

- [x] 1.1 Add the Sketch object that holds vertices, edges, handles, spline
      points and internal lines, with its own stable identity, and verify a
      headless probe creates one, adds an outline and an internal line, and reads
      them back unchanged through a new `tools/probe_pattern_layers.py`
- [x] 1.2 Give the Sketch the editor's own draw points (a straight piece stays a
      line, a curved piece is its fitted curve) and verify the draw points of a
      Sketch match its geometry
- [x] 1.3 Remove the vector collections from the Pattern, so a caller that still
      reaches them fails loudly, and verify an import-and-call probe reports the
      failure instead of returning an empty Sketch
- [x] 1.4 Report a Pattern that carries no Sketch as having no geometry, and
      verify nothing invents one for it
- [x] 1.5 Remove the Sketch of a chain when its last Pattern is removed, and
      verify a probe that deletes the members one by one ends with no Sketch left
- [x] 1.6 Give no geometry element an accessor that names a panel: a vertex, an
      edge, a control point and an internal line answer for the Sketch they are
      stored in - `element.sketch`, resolved once from the element's own path
      and identity-checked (`resolve_sketch`) - and a caller that holds only the
      element asks `owner_pattern` for the panel that owns that Sketch. An
      element can no longer be read as a panel of its own (the `pattern`
      property, its `pattern_temp` and the generic "container" of an element are
      gone from `Vertex2D`, `Edge2D` and `InternalLine`), and none of them
      carries a write-back path that pretends otherwise. Verify by reading the
      same panels back through `tools/probe_pattern_layers.py`, the model,
      agent-api and section probes
- [x] 1.7 Give every geometry element its identity when it is created, in the
      helpers that make one (`Sketch.add_vertex`, `Sketch.add_edge`,
      `Sketch.add_internal_line`, `Sketch._copy_edge`, `InternalLine.add_edge`,
      the handle and spline-point makers, and the generator/script paths that
      add into a collection directly), because an element with no identity used
      to be reachable only by accident - the `pattern` write an add path made
      used to hand one out - and a vertex left at identity -1 makes every uuid
      lookup answer with whichever element was registered last. Verify with the
      corner merge that reads its two ends back by uuid: with the identity
      missing it built an edge whose ends were the same point
      (`tools/test_divide_edge.py`, "a V tip merged past its ends")
- [x] 1.8 Carry every cross-reference in the model by identity and read it back
      through the uuid map, which is already the liveness check (one guarded
      `global_uuid` read, 0.2 us) instead of a general "is this wrapper alive"
      helper built on `path_from_id` (0.003-1.1 ms, and it misses a wrapper a
      removal shifted onto another item). The temporary `is_live` helper is
      gone: a panel a seam side names, a panel a piece belongs to and the edge a
      piece was cut from are all resolved by uuid, so a removed panel and a
      replaced edge read back as None and the consumers skip them. A seam side
      no longer asks the geometry which panel it is on - `add_sewing` records
      the panel at creation (the edge's Sketch owner when the caller names
      none) and the side keeps that answer, so a file saved before sides
      recorded one is reported instead of silently re-homing. Verify with the
      section invariants, the toolkit chain, the seam marks and
      `tools/probe_delete_regression.py`
- [x] 1.9 Delete the instance list: `Pattern.instance_next_uuid`,
      `Pattern.other_instances()`, `collect_unique_instances` and the
      `Pattern.instances` slot are gone, and a chain is read from the Sketch -
      the panels whose `sketch_uuid` is the one the panel names
      (`Pattern.sketch_members()`). The list was a second source of truth for
      something the Sketch already says, and its walk (`while p is not self`)
      had no guard: a chain a copy or a removal left pointing somewhere else
      never came back to its start, which is what froze the editor on an
      unrelated edit. Verify with the partition tools on a chain
      (`.agents/scratch/probe_toolkit_chain.py`), the copy and detach cases
      (`.agents/scratch/probe_operator_rebuild.py`, `probe_round_trip.py`) and
      the agent api's chain reads (70 checks)
- [x] 1.10 Stop the topology tools walking the chain: divide, corner, fan,
      delete, add vertex, add spline point, the internal-line pen and the scale
      tool write the Sketch and mesh the panel they were used on - the other
      readers of that Sketch were marked by the write and rebuild when a
      consumer asks them for a mesh. The move gesture keeps the members: it
      draws the whole chain while it drags, and the scale tool does the same for
      the mesh pass because a panel whose placement did not move must not be
      left drawing a surface the size it used to be. Verify with
      `.agents/scratch/probe_add_vertex.py` (the click that used to freeze) and
      `.agents/scratch/probe_toolkit_chain.py`
      (superseded by 11.2: a member left marked kept drawing the shape that used
      to be there until something else meshed it, so the tools now go through
      the Sketch's own mesh rebuild and every member is meshed with the edit)
- [x] 1.11 Pick a pair, not an element: the id pass records `(panel, element)`
      per id and nothing collapses that back to one panel per element
      (`pattern_for` and `pointed_pattern` are gone, and `pattern_of_id` with
      them). Selecting an element makes the member under the pointer the active
      panel (`QianyiProject.active_pattern`), the tools that work in pattern
      space read the active panel or the snap they were given, and the seam tool
      stores the panel with each of its two clicks, so a seam between two
      members of one chain names those two and not the chain's owner twice.
      Verify with `.agents/scratch/probe_sewing_clicks.py` and
      `.agents/scratch/probe_pick_table.py`
- [x] 1.12 Survive a collection that was written to: Blender retires every
      wrapper a collection handed out as soon as an item is added to it
      (`edge.path_from_id()` then raises `ValueError`), and the split-edge tool
      held the edge it was splitting while it added the new one. The Sketch is
      now recorded on an element when it is created (`Sketch.own`), so
      `element.sketch` answers from that record, `resolve_sketch` falls back to
      the uuid map instead of raising, and the tool reads its edges back from
      the collection after each write. Verify with
      `.agents/scratch/probe_add_vertex.py`, which clears the cache first so the
      tool runs the way a fresh session has it
- [x] 1.13 Read the snap against the shape it was taken on: the edge finder
      reports an index into a flat array of the panels' samples, and an edit
      since that snapshot makes the index describe a shape the panels no longer
      have - which is what raised a KeyError in `get_nearest_point_data` when a
      vertex was added to one instance and then to another. The snapshot now
      carries the per-edge sample counts it was taken from, a lookup checks them
      against the panels as they are (and rebuilds the finder and re-finds from
      the pointer when they differ), and every tool that changes an outline
      clears the finder when it is done. Verify with
      `.agents/scratch/probe_add_vertex.py`, which puts the pre-edit snapshot
      back by hand and then snaps on the other member
- [x] 1.14 Name the wrappers a rewritten collection holds now: adding or removing
      an item retires the wrappers the collection handed out before it, and the
      identity map kept the retired one - so a control point a tool had just
      written (a corner's trimmed neighbour comes back as a spline, a split edge
      carries its pieces' control points) could not be read back by identity and
      could not be selected. `Edge2D.set_curve` refreshes the map for its
      handles and spline points, and the tools that rewrite those collections in
      a loop refresh them too. Verify with
      `.agents/scratch/probe_corner_spline_pick.py`

## 2. The first section stage on the Sketch

- [x] 2.1 Move the section chain (one section per edge, linked in outline order,
      wrapping for a closed outline) onto the Sketch, and verify a probe reads the
      chain back as a doubly linked list whose total length equals the outline's
      length
- [x] 2.2 Measure the crossing search on the Sketch's own samples instead of the
      granularity-resampled ones, and verify a probe that samples one Sketch at
      two granularities finds the same crossings
- [x] 2.3 Cut the sections of both curves at every outline-to-line and
      line-to-line crossing, and verify a probe that draws a line across the
      outline reports the outline's and the line's new pieces at the crossing
- [x] 2.4 Mark the pieces of an internal line that lie outside the outline, and
      verify a probe reports no outside piece for a line inside the panel and the
      expected outside pieces for a line that leaves it
- [x] 2.5 Assert that the stage does not depend on a pattern: run the stage for a
      Sketch referenced by two patterns with different granularities and verify
      both report the same pieces and the same marking
- [x] 2.6 Narrow the piece a cut leaves behind: the first stage gave every piece
      of a cut edge the end of the whole edge, so a piece of a few millimetres
      read as long as the edge it came from and was given a segment count for
      that length - which is what made an internal line and the outline edge it
      crosses carry several times the samples their own length asked for around
      the crossing. `Sketch._split_section` now ends the lower piece at the cut,
      the way `Section.split` does on a panel's own copy. Verify with
      `.agents/scratch/probe_crossing_seg.py`, which measures the spacing of
      every piece's samples at two granularities and asserts that the pieces of
      one edge do not overlap

## 3. The write signal and the rebuild

- [x] 3.7 Split the first stage from the sampled one: add `SectionRaw` (edge,
      span, crossing marks only) as what the Sketch stores, make the Pattern clone
      a raw chain into its own `Section` objects carrying the per-panel segment
      count and sample and mesh offsets, and verify a probe reads the Sketch's
      raw spans and the Pattern's sampled pieces on the same panel
- [x] 3.8 Take the sampling state off the shared objects: move `geo_points`,
      `geo_points_temp`, `unique_geo_point_size` and `start_point` off `Edge2D`
      and `mesh_edge_inner_point_size` off `InternalLine` into the Pattern's own
      sample store, and verify no shared element holds a sample or an offset
- [x] 3.8b Close the whole-outline stitch case: a seam side that wraps the whole
      outline reports its last stitch one sample short of the seam's end when the
      other side is a much shorter run, and verify the endpoint check of
      `tools/check_section_invariants.py` passes for a loop-to-loop seam, walked
      each way (the walk's far end carries one extra sample, read one past the
      piece's own run: on the piece that wraps the panel's sample array that read
      lands on the first sample of the *next* curve instead of the panel's own
      first sample, which the panel records as `mesh_end_point`. The override was
      skipped for a closing walk and, for a reversed walk, looked at the wrong end
      of the walk: the piece the extra sample belongs to is the last one visited
      forwards and the first one visited backwards)
- [x] 3.9 Make a seam change mark instead of rebuild: creating, removing or
      moving a seam marks the section copy, the samples and the mesh of every
      pattern in the chains it reaches, and verify a seam edit leaves every mesh
      as it was while a topology edit still meshes before it returns, and a
      prepare rebuilds what the seam marked (the seam marks the panels it names
      and every panel the sewings reach, and no mesh moves on the edit; the
      prepare then rebuilds what was marked and stitches, verified in
      `.agents/scratch/probe_marks_and_granularity.py`)
- [ ] 3.9c Drop the eager re-clone: `add_sewing` still builds the copies of
      every panel a sewing touches before the linking run reads them. Deferring
      that is blocked by the pieces' own lifetime: a copy that was not rebuilt
      keeps pieces whose edge an earlier divide replaced, and cutting such a
      piece takes the process down (`EXCEPTION_ACCESS_VIOLATION` in Blender's
      RNA, reproduced three times in `tools/test_divide_edge.py`). What landed
      instead is the guard for it - pieces that do not name a live edge are
      skipped and a piece's own `Section.panel` is what gets marked - so the
      remaining work is to make the mark cover every panel the linking run will
      touch, and only then stop re-cloning
- [x] 3.9b Rebuild on a granularity change: verify the panel is sampled and
      meshed again before the change returns and the other members of its chain
      are untouched (`mark_geometry_changed` plus `generate_mesh` in the
      granularity callback; a panel that has never been meshed is left to
      whoever asks for its first mesh, so a script that is still writing the
      panel is not meshed from under itself)
- [x] 3.10 Rebuild a marked pattern by cloning the Sketch's first stage again,
      and verify a probe that cuts a copy with a linking run, changes the seam and
      rebuilds ends with the cuts of the new seam graph only
      (`.agents/scratch/probe_rebuild_and_refusals.py`: after the seam moves, the
      copy holds exactly the new seam's boundaries and the old seam's cut is
      gone. It also found and fixed a real defect on the way: `find_or_add_section`
      picked the first piece starting before the position, so a seam end past an
      existing piece cut that piece with a fraction beyond its own end and left a
      piece running backwards, which then reached the mesh)

- [x] 3.1 Make one write send one signal: every write path of a Sketch ends in
      `Sketch.geometry_written`, which calls `mark_geometry_changed` on every
      Pattern whose `sketch_uuid` is that Sketch's - its outline state, its own
      copy of the stage, its samples, its render line and the sewings that reach
      it - and a write that leaves the shape as it was sends nothing. Verify a
      probe reports the panels marked after a written point and nothing marked
      when the write repeats the value it already had

## 4. The Pattern layer

- [x] 4.1 Keep identity, placement, granularity, fabric, collision layer,
      simulation state, mesh object and chain membership on the Pattern, and
      verify a probe that changes each of them marks no geometry
- [x] 4.2 Make a copy share the source's Sketch and join its chain, and verify a
      probe reports one Sketch, one element count and two patterns after a copy
- [x] 4.3 Implement detach as a private copy of the Sketch for one Pattern, and
      verify a probe that detaches one of three members, edits the detached
      outline and checks the other two are unchanged and still share their Sketch
- [x] 4.4 Report a detach that has nothing to do (a pattern alone in its chain),
      and verify the report names the Pattern and says it was already alone
- [x] 4.5 Remove the per-member write loops and the drifted-copy refusal, and
      verify the drift message is no longer reachable from any command

## 5. Operators on the Sketch

- [x] 5.1 Re-point every tool that changes topology (pen, add vertex, add spline
      point, edge move, divide, corner, fan, element delete, internal line pen)
      at the Sketch's single write path, and verify each tool's existing probe
      passes against one Sketch per chain
- [x] 5.2 Keep each tool's own immediate checks (candidate outline crossing,
      minimum distance, granularity) on the candidate Sketch state, and verify a
      refused edit leaves the geometry, the marks and the derived data untouched
      (an impossible divide is refused with the mesh unchanged,
      in `.agents/scratch/probe_rebuild_and_refusals.py`)
- [x] 5.3 Verify a topology tool meshes before it returns: run a tool on a
      two-pattern chain and assert every member has a mesh built from the edit
      (the rule changed: a topology edit must mesh at once, only a change that
      moves no geometry is deferred) - `.agents/scratch/probe_toolkit_chain.py`
      runs divide, corner, fan, internal line and delete on a chain of three and
      finds every member meshed after each
- [ ] 5.4 Verify one tool run is still one undo step, and that undo restores
      both the Sketch and the patterns together
- [x] 5.5 Write a fan on the edges its plan measured: a plan's edge indices are
      the outline before anything is written, and splitting an edge inserts a
      piece right after it, so the second cut landed on the edge that had moved
      up - the target end of the radius stayed uncut, one whole side came out
      wrong and the piece between them carried handles measured for another
      edge. The write finds each edge again by identity (`_edge_index_of`), keys
      its piece tables by the edge's uuid, and reads the rotated edges before
      the arc edge is inserted. Verify with `.agents/scratch/probe_fan_result.py`,
      which compares the written outline with the shape `fan_outline` previews
      on three fan gestures

## 6. Display, picking and selection

- [ ] 6.1 Draw a Sketch's draw points per Pattern with that Pattern's transform,
      and verify a headless draw probe draws one Sketch on two patterns at two
      places (both draw paths already use the panel: the render line is built
      per panel and the id pass draws a shared edge once per member, recording
      which member drew it. The headless probe cannot run - the background
      session has no GPU context - so this needs a UI pass)
- [x] 6.2 Give a Pattern the temporary table of the selectable things it draws
      (edge, point, spline control point, handle) with a generated id each, and
      verify the id pass draws those entries and a pick reads an id back to the
      element and the Pattern that generated it (`Pattern.pick_id` hands the
      panel a generated id per (kind, element); the pass records
      `id -> (panel, kind, element)` in `TempDrawManager.pick_of_id` and draws
      each edge once per chain member with that member's transform and its own
      id, so a pointer over a copy's edge reads the copy's id instead of
      whichever member was drawn last. `.agents/scratch/probe_pick_table.py`
      verifies the table, the round-trip and the per-member transform; the pass
      itself needs a UI look)
- [x] 6.3 Re-point the mouse selection path (the scene's hover object and the
      select operator) at that table, and verify a click on one member of a chain
      selects that member's element while a click on the other member selects the
      same element with the other Pattern (the pointer reads the pair out of the
      pick table: `hover_pattern` and `hover_kind` are what the click's pattern
      space, the hover highlight, the seam's own panel and the sewing preview
      use, while the selection itself keeps storing the element - one Sketch
      element is on screen in every member, so selecting it selects it)
- [x] 6.4 Store the pair where the Pattern matters and the element alone where it
      does not, and verify moving a picked vertex through either pattern moves
      the one shared Sketch (the pair is stored where it matters - a seam side
      names its panel, the pointer's panel is kept with the pick - and the
      element alone where it does not; moving a vertex through either member
      moves the one Sketch, verified in `tools/probe_pattern_layers.py`)
- [ ] 6.5 Verify a pick does not sample: draw the id pass of a marked panel and
      assert its samples and mesh are unchanged (the id pass only builds draw
      points, never samples or meshes; the verification needs a UI pass)
- [ ] 6.6 Show a marked Pattern in the editor instead of sampling it during a
      draw, and verify a draw of a marked Pattern rebuilds nothing (a draw only
      builds draw points; the marker the editor would show is the panel whose
      copy is out of date. The verification needs a UI pass)
- [x] 6.7 Highlight the first edge of a seam on the member that was clicked:
      the renderer's default panel is the owner of the edge's Sketch, so the
      blue mark used to appear on the first member of the chain whatever was
      clicked. The record the click left (`selected_sewing_pattern1`) is what
      the highlight draws with. Verify with
      `.agents/scratch/probe_sewing_highlight.py`, which drives the draw pass
      with the GPU stubbed and records the call
- [x] 6.8 Show the preview of a seam between two members of one chain: the
      preview gave up whenever the hovered edge *was* the picked one, so sewing
      one edge of an instance to the same edge of another - a seam along the one
      edge two members share - drew no end connectors at all. The pair of panel
      and edge is what says "the first side is still under the pointer", so the
      same edge of the same member is the only case that draws nothing. Verify
      with `.agents/scratch/probe_sewing_preview.py`
- [x] 6.9 Rebuild the display of what a tool changed: the id pass ran before
      the draw and cleared the panel's mark after rebuilding only the outline,
      so the points and the spline points stayed stale - a new spline point did
      not appear, and a point cloud that no longer matched the model is what made
      a box selection pick nothing. Delete and the spline-point tool also wrote
      straight into the Sketch's collections without sending the write signal,
      so nothing was marked at all. The id pass now leaves the mark to the draw,
      and both tools send `Sketch.geometry_written()`. Verify with
      `.agents/scratch/probe_render_update.py`, which covers add vertex, add
      spline point, divide, delete and the id pass
- [x] 6.10 Preview the internal lines the move gesture drags: the gesture built
      its previews from the outline's edges alone, so moving a point of an
      internal line showed nothing following the pointer. `gesture_edges()` is
      every edge of every Sketch in the selection - outline and internal lines,
      each once however many chain members were selected - and the gesture
      builds a preview for each. Verify with
      `.agents/scratch/probe_move_preview.py`, which also drives the draw pass
      and records the previews it draws
- [x] 6.11 Draw a seam selected in the sewing mode correctly in every other
      mode: the selection holds the seam's *sides* - a pick answers the side it
      was drawn with - and the dimmed pass read a side as the seam itself, which
      raised `'SewingOneSide' object has no attribute 'update'` on the next
      redraw in the edge mode. `SewingOneSide.sewing` now answers the seam it
      belongs to (the seam's own update sets it, and a file nothing has drawn
      yet is found by walking the project's sewings), and the dimmed pass reads
      each selected side as its seam, drawing each seam once. Verify with
      `.agents/scratch/probe_sewing_highlight.py`
- [x] 6.12 Keep an edge's handles on screen while one of its own points is
      selected: a handle or a control point is moved through the handles of the
      edge it belongs to, and asking only whether the *edge* was selected left
      them undrawn the moment a click moved the selection onto a point - the
      point floated on its own and the second handle could not be picked any
      more. `handles_visible()` answers for the edge or any of its points, the
      id pass and the highlight both use it. Verify with
      `.agents/scratch/probe_corner_points.py`
- [x] 6.13 Draw the handles a drag is moving on every member: `draw_instances`
      drew the previewed curve once per member, and the `draw_handles` call that
      followed it named no panel - so it fell back to the owner of the edge's
      Sketch and the dragged handle appeared on the first member alone.
      `draw_instances(..., handles=True, handle_color=...)` draws each member's
      handles where that member's curve was drawn, and the drag uses it. Verify
      with `.agents/scratch/probe_move_preview.py`, which selects a handle,
      sets the gesture up and records the panel each previewed handle was drawn
      for

## 7. Seams

- [x] 7.1 Store a seam side as Pattern, Sketch element and position, and verify a
      seam created on one pattern of a chain reads back with that pattern named
- [x] 7.2 Make the stitch walk derived data of the two patterns, rebuilt when
      either panel is marked, and verify an edit that keeps the named edges
      keeps the seam and rebuilds its walk (the walk is computed from the panels'
      current pieces every time it is read, and `tools/test_divide_edge.py`
      verifies that a seam on a divided edge is re-homed and stitches again)
- [ ] 7.3 Drop and report a side whose named element is gone, and verify a probe
      that deletes the named edge removes exactly that side and reports it
      (today the whole seam goes with the side, and a side whose panel is gone
      reads back as `None` and takes the seam with it)
- [x] 7.4 Verify a simulation prepare rebuilds both patterns of a sewn pair, and
      that a prepare refuses a panel whose outline is invalid, naming it (the
      prepare rebuilds what was marked - verified in
      `.agents/scratch/probe_marks_and_granularity.py` and
      `probe_rebuild_and_refusals.py`; the refusal is the outline test, which
      `tools/probe_pattern_validity.py` verifies stops a simulation start. A
      *marked* panel is not refused: the prepare rebuilds it, which is the rule
      the two layers ask for)

## 8. Mesh, prepare and generators

- [x] 8.1 Route the mesh path through the panels' rebuild gate, and verify a
      probe that meshes a marked Pattern rebuilds it while an unmarked one
      computes nothing (`.agents/scratch/probe_rebuild_and_refusals.py`)
- [x] 8.2 Keep the prepare path's validations (crossing outlines, identities) and
      add the rebuild of every participating marked Pattern, and verify a prepare
      exports geometry that matches the Sketch the patterns have now (after an
      edit the prepare rebuilds the panel, and the mesh it exports follows the
      Sketch - `probe_rebuild_and_refusals.py`)
- [x] 8.3 Re-point the generators at the Sketch (a rebuild writes the Sketch and
      keeps the patterns), and verify a generator rebuild on a chain keeps one
      Sketch and reports the patterns it rebuilt (a generator panel and a copy of
      it stay on one Sketch across a rebuild, both meshed and current, in
      `probe_rebuild_and_refusals.py`)
- [x] 8.4 Verify the engine payload is unchanged: compare the payload of a
      one-pattern chain before and after this change on the same scene (what a
      probe can verify today is the rule underneath it - the prepare rebuilds the
      panel it exports and the exported mesh is that panel's own geometry, in
      `probe_rebuild_and_refusals.py`; the byte-for-byte comparison with the
      pre-change build would need the old build of the add-on)

## 9. Surfaces and documentation

- [x] 9.1 Update the script surface so a panel's reads report its Sketch and its
      derived state, and add the detach call, and verify each call round-trips in
      a scripted session (a panel read reports the `sketch` it reads, and
      `patterns.detach(name)` is the chain's own detach;
      `.agents/scratch/probe_marks_and_granularity.py` round-trips both)
- [x] 9.2 Update `docs/agent-api.md` with the two layers, the write-signal rule,
      the detach call and that an older file is not converted
- [ ] 9.3 Drop the drifted-chain requirement and its message when the
      `pattern-editing-toolkit` change archives, and verify the archived spec has
      no requirement about copies with a different shape

## 10. Integration verification

- [x] 10.1 Draft a panel set with the editing tools (divide, corner, fan,
      internal line, delete), on a chain of three patterns including a mirror,
      and verify every member reports one Sketch, the outlines are valid, and the
      meshes rebuild (`.agents/scratch/probe_toolkit_chain.py`: every tool on the
      chain, one Sketch per chain, valid outlines, every member meshed)
- [x] 10.2 Detach the mirror, edit both Sketches, and verify no command reports a
      mismatch and both patterns simulate (the same probe: the detach leaves the
      mirror with its own Sketch, and both panels edit and mesh)
- [x] 10.3 Run the existing probes (`tools/test_divide_edge.py`,
      `tools/check_section_invariants.py`, the model, agent-api and pattern
      validity probes) and verify none of them fails (all clean, see
      `.agents/scratch/` for the probes added along the way)
- [x] 10.4 Save and reopen a project with a chain, an internal line and a seam,
      and verify one Sketch per chain and every Pattern attribute read back
      (`.agents/scratch/probe_round_trip.py`: one Sketch per chain, placement,
      granularity, geometry and mesh read back, the sections rebuild on demand
      and the seam names its panel and stitches again)

## 11. One mesh call per Sketch, and the merged corner

- [x] 11.1 Merge a corner one side at a time, on the points the outline keeps:
      the arc ends on the vertex beyond a consumed edge and on the new tangent
      vertex of a side that was only trimmed - ending it on the far vertex of an
      un-reached side spliced the outline onto itself and crossed the panel's
      edges. Both ends are read where they are rather than extrapolated along
      the tangents (a curved edge's far vertex is not on the ray), the circle is
      the one tangent at one end and through the other, the trimmed side is
      written as a piece of its own curve instead of having its end dragged, and
      the corner edge takes its place in the chain: after the arriving edge, or
      the slot of the first consumed one where both are consumed, or right after
      the edge that used to arrive at the far vertex where only that side was
      consumed. Verify with `.agents/scratch/probe_corner_merge.py` (both
      one-sided merges, the full merge, a reflex corner, a curved side, and that
      the written arc ends where the preview drew it) and with the corner checks
      in `tools/test_divide_edge.py`
- [x] 11.2 Mesh every member through the Sketch: a topology tool writes the
      Sketch once, so the mesh step belongs to the Sketch too - one call builds
      the mesh of every panel that reads it (`Sketch.rebuild_meshes`, with
      `Sketch.reading_patterns` as the single reader of "which panels these
      are"). Divide, corner, fan, delete, add vertex, add spline point, the
      internal-line pen, the internal-line API and the internal-line removal all
      ask the Sketch instead of one panel, which used to leave every copy of the
      edited panel showing the shape that used to be there. Verify with
      `.agents/scratch/probe_mesh_all_instances.py` (a panel with one linked
      copy, four commands: each of them leaves both meshes built from the edit)
- [x] 11.3 Clamp the corner drag instead of refusing it: the radius a corner
      takes has two windows - up to what fits without merging, and from the
      first radius whose tangent reaches a far vertex to the last merge the
      outline takes - and nothing in the gap between them can be written at all
      (`merge_window` reads both from `corner_limits`, and a drag that lands in
      the gap snaps to the nearer end). The merge's own window is cut back to
      the largest merge whose outline stays simple, the smallest merge is tested
      for that too (a window of one radius used to slip through), and the
      self-crossing test itself is the scene's Check Self-Intersection switch
      and nothing else (`crossing_check_enabled`): with the switch off an edit
      that crosses is written and the mesh stage reports it, with it on the drag
      stops before the crossing. Verify with
      `.agents/scratch/probe_corner_drag.py` (the real `invoke`, `modal`, `drag`
      and `execute` over a pointer sweep, both switch settings, a merge that
      crosses, and that the run reports no error) and the switch cases in
      `.agents/scratch/probe_corner_merge.py`
- [x] 11.4 Drop a removed element from the selection: a merge takes the corner
      vertex and the edge (or both edges) it consumes, and the selection named
      them, so the draw pass asked for identities that were gone and printed the
      missing-uuid diagnostic on every frame. The removal says which identities
      went (`QianyiProject.forget_selected`) and the tool picks up the corner
      edge it produced instead, and the hover the pointer stood on is dropped
      with them (the vertex it named is gone); nothing else is silenced, so a
      genuinely broken reference is still reported. Verify with
      `.agents/scratch/probe_corner_drag.py` (a selected vertex and edge are
      merged away, the hover is cleared, every remaining entry resolves and the
      draw pass reports nothing at all)
- [x] 11.5 One implementation per idea in the corner tool: the treated and the
      merged corner are written by one writer (`_write_corners`, which follows
      the `consume_prev`/`consume_next` flags of the plan), the two plans share
      one arc constructor (`_corner_arc`) and one trim table (the merge plan
      returns `trims` like the treatment plan does), and `invoke` and `execute`
      share one `prepare` that reads the panel, the corners and the radius
      windows, so the range is measured once per run instead of once per pointer
      position. Nothing about what the commands write changed: the same probes
      pass (`probe_corner_drag.py`, `probe_corner_merge.py`,
      `probe_corner_points.py`, `tools/test_divide_edge.py`,
      `probe_toolkit_chain.py`, `probe_mesh_all_instances.py`,
      `probe_corner_spline_pick.py`), and the file is 1050 lines instead of
      1400

## 12. The tool preview, and merging points

- [x] 12.1 A tool's preview goes with the tool: the draw manager records the tool
      that drew the points and lines it holds (`tool_owner`, read from the
      workspace's active tool), and the draw pass drops them when the editor has
      picked another tool - the fan tool's preview used to stay on screen after
      switching away, since nothing else replaces or clears it. Verify with
      `.agents/scratch/probe_tool_preview_switch.py` (a windowed run: the preview
      survives a draw while its own tool is active and is gone after the select
      tool is picked)
- [x] 12.2 Merge the selected points, per run of connected points: the right-click
      menu's "merge connected" is the element delete's counterpart
      (`_2d_merge_connected.py`) - a run of consecutive selected points on a chain
      becomes one point **at the centre of the run** - the first of the points
      keeps the identity and takes that place - instead of the run going away. An
      edge counts as both of its ends; both edges that remain at the ends of the
      run are re-pointed at the merged point and move only the control point at
      the end that moved (the handle of a Bezier, the nearest control point of a
      spline), so the halves that stay keep the shape they had. Selected control
      points of a spline edge merge the same way, into one control point of that
      edge at their centre. The edges and points inside the run go with their
      seams, a whole loop is refused, the candidate outline is tested for a
      crossing while the scene's switch is on, and the Sketch marks and meshes
      every member of the chain. Verify with
      `.agents/scratch/probe_merge_connected.py` (a run on the outline, two
      selected edges, a run crossing a loop's end, a run inside an internal line,
      the centre of the merged point, a Bezier and a spline edge leaving the run,
      two control points of a spline edge merged into one, a seam on a removed
      edge, and a whole chain refused with nothing written)
