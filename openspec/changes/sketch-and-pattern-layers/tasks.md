## 1. The shape layer

- [ ] 1.1 Add the shape object that holds vertices, edges, handles, spline
      points and internal lines, with its own stable identity, and verify a
      headless probe creates one, adds an outline and an internal line, and reads
      them back unchanged through a new `tools/probe_pattern_layers.py`
- [ ] 1.2 Implement adoption: a piece with its own vector collections and no
      shape gets a private shape built from them, and verify a probe that builds
      a piece the old way adopts it once, keeps the positions and is reported as
      alone in its chain
- [ ] 1.3 Give the shape the editor's own draw points (a straight piece stays a
      line, a curved piece is its fitted curve) and verify the draw points of an
      adopted shape match the geometry it was adopted from
- [ ] 1.4 Remove the vector collections from the piece, so a caller that still
      reaches them fails loudly, and verify an import-and-call probe reports the
      failure instead of returning an empty shape
- [ ] 1.5 Remove the shape of a chain when its last piece is removed, and verify
      a probe that deletes the members one by one ends with no shape left

## 2. The first section stage on the shape

- [ ] 2.1 Move the section chain (one section per edge, linked in outline order,
      wrapping for a closed outline) onto the shape, and verify a probe reads the
      chain back as a doubly linked list whose total length equals the outline's
      length
- [ ] 2.2 Measure the crossing search on the shape's own samples instead of the
      granularity-resampled ones, and verify a probe that samples one shape at
      two granularities finds the same crossings
- [ ] 2.3 Cut the sections of both curves at every outline-to-line and
      line-to-line crossing, and verify a probe that draws a line across the
      outline reports the outline's and the line's new pieces at the crossing
- [ ] 2.4 Mark the pieces of an internal line that lie outside the outline,
      and verify a probe reports no outside piece for a line inside the panel and
      the expected outside pieces for a line that leaves it
- [ ] 2.5 Assert that the stage does not depend on a panel: run the stage for a
      shape referenced by two pieces with different granularities and verify both
      report the same pieces and the same marking

## 3. Revision and the bake contract

- [ ] 3.1 Add the shape revision, raise it on every shape write, and verify a
      probe reports an unchanged revision for a write that sets a value it is
      already set to
- [ ] 3.2 Add the bake record to the piece (the revision the derived data was
      baked from plus the reason a bake did not run) and define stale as "the
      record differs from the shape revision", and verify a probe sees a piece as
      stale after an edit and current again after a bake
- [ ] 3.3 Implement `bake(piece)` as the single entry point for derived data
      (samples, mesh, stitch walk, payload) and verify a probe that bakes twice
      after one edit computes once and leaves the same result
- [ ] 3.4 Make a missing bake record read as stale, so undo, redo and a file
      reload rebuild instead of trusting a blank cache, and verify a probe that
      clears the session data and then reads a piece
- [ ] 3.5 Implement the refusing bake: a crossing or degenerate outline keeps
      the last good derived data, records the reason and is reported as stale,
      and verify a probe that crosses an outline, reads the piece, fixes the
      outline and reads it again
- [ ] 3.6 Delete the cache flags the revision replaces, and verify no remaining
      caller reads or writes one (a grep of the model, the operators and the
      gizmos comes back empty)

## 4. The piece layer

- [ ] 4.1 Keep identity, placement, granularity, fabric, collision layer,
      simulation state, mesh object and chain membership on the piece, and verify
      a probe that changes each of them leaves the shape revision alone
- [ ] 4.2 Make a copy share the source's shape and join its chain, and verify a
      probe reports one shape, one element count and two pieces after a copy
- [ ] 4.3 Implement detach as a private copy of the shape for one piece, and
      verify a probe that detaches one of three members, edits the detached
      outline and checks the other two are unchanged and still share their shape
- [ ] 4.4 Report a detach that has nothing to do (a piece alone in its chain),
      and verify the report names the piece and says it was already alone
- [ ] 4.5 Remove the per-member write loops and the drifted-copy refusal, and
      verify the drift message is no longer reachable from any command

## 5. Operators on the shape layer

- [ ] 5.1 Re-point every tool that changes topology (pen, add vertex, add spline
      point, edge move, divide, corner, fan, element delete, internal line pen)
      at the shape's single write path, and verify each tool's existing probe
      passes against one shape per chain
- [ ] 5.2 Keep each tool's own immediate checks (candidate outline crossing,
      minimum distance, granularity) on the candidate shape state, and verify a
      refused edit leaves the shape revision and the derived data untouched
- [ ] 5.3 Verify a topology tool performs no derived work: run a tool on a
      two-piece chain and assert the shape revision rose by one and both meshes
      are the ones they were
- [ ] 5.4 Verify one tool run is still one undo step, and that undo restores
      both the shape and the pieces together

## 6. Display, picking and selection

- [ ] 6.1 Draw a shape's draw points per piece with that piece's transform, and
      verify a headless draw probe draws one shape on two pieces at two places
- [ ] 6.2 Resolve a pick to the shape element plus the piece it was picked on,
      and verify a pick-cycle probe returns the same element for both pieces and
      the piece that was picked
- [ ] 6.3 Store the pair where the piece matters and the element alone where it
      does not, and verify moving a picked vertex through either piece moves the
      one shared shape
- [ ] 6.4 Mark a stale piece in the editor instead of sampling it during a
      draw, and verify a draw of a stale piece does not bake (the bake record is
      unchanged after a redraw)

## 7. Seams

- [ ] 7.1 Store a seam side as piece, shape element and position, and verify a
      seam created on one piece of a chain reads back with that piece named
- [ ] 7.2 Make the stitch walk derived data of the two pieces, rebuilt when
      either shape revision moves, and verify an edit that keeps the named edges
      keeps the seam and rebuilds its walk
- [ ] 7.3 Drop and report a side whose named element is gone, and verify a probe
      that deletes the named edge removes exactly that side and reports it
- [ ] 7.4 Verify a simulation prepare bakes both pieces of a sewn pair, and that
      a chain with one stale piece refuses the prepare with that piece named

## 8. Mesh, prepare and generators

- [ ] 8.1 Route the mesh path through `bake(piece)`, and verify a probe that
      meshes a stale piece reports the bake and a current piece does not
- [ ] 8.2 Keep the prepare path's validations (crossing outlines, identities)
      and add the bake of every participating stale piece, and verify a prepare
      exports geometry that matches the shape the pieces have now
- [ ] 8.3 Re-point the generators at the shape layer (a rebuild writes the shape
      and keeps the pieces), and verify a generator rebuild on a chain keeps one
      shape and reports the pieces it rebuilt
- [ ] 8.4 Verify the engine payload is unchanged: compare the payload of a
      one-piece chain before and after this change on the same scene

## 9. Surfaces and documentation

- [ ] 9.1 Update the script surface so a panel's reads report its shape and its
      derived state, and add the detach call, and verify each call round-trips in
      a scripted session
- [ ] 9.2 Update `docs/agent-api.md` with the two layers, the revision rule, the
      detach call and what an older file loads as
- [ ] 9.3 Drop the drifted-chain requirement and its message when the
      `pattern-editing-toolkit` change archives, and verify the archived spec has
      no requirement about copies with a different shape

## 10. Integration verification

- [ ] 10.1 Draft a panel set with the editing tools (divide, corner, fan,
      internal line, delete), on a chain of three pieces including a mirror, and
      verify every member reports one shape, the outlines are valid, and the
      meshes rebuild
- [ ] 10.2 Detach the mirror, edit both shapes, and verify no command reports a
      shape mismatch and both pieces simulate
- [ ] 10.3 Run the existing probes (`tools/test_divide_edge.py`,
      `tools/check_section_invariants.py`, the model, agent-api and pattern
      validity probes) and verify none of them fails
- [ ] 10.4 Verify the adoption path with a scene saved by the current build: the
      outline, internal lines, sewings and meshes read back and a simulation
      steps
