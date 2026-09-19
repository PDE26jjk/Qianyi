## 1. Extract what only the operators have

- [x] 1.1 Move the copy, mirror and instance logic out of `_2d_pattern_copy_instance.py` into a model function (panel creation, placement, the `instance_next_uuid` chain, geometry copy, mesh build) and re-point the operator at it; verify with a scripted scene that an instance copy and a mirror copy are created, that both report the same chain, and that the operator's own path still produces the same result (`Pattern.copy_pattern` + `_copy_geometry_from`; the probe creates a mirror copy, reads the chain from both ends, and edits the source to check the copy follows. The operator is now three lines and calls the model function; its own click-through still needs a viewport)
- [x] 1.2 Add a model function that builds an internal line from a polyline (edges, handle types, membership) and re-point the internal line pen at it; verify a scripted panel gains one internal line and its mesh reflects the cut (`Pattern.add_internal_line`; the probe adds one line - mesh 258 -> 254 vertices - and removes it again, back to 4 vertices and 258)
- [x] 1.3 Add a model function that writes one edge as a straight line, a Bezier or a spline (handle positions, handle types, spline points) and re-point the code paths that do it today in the pen and copy operators; verify each of the three kinds lands and reports back its kind (`Edge2D.kind` + `Edge2D.set_curve`; the copy path and `generators._edge_kind` both use it, and the probe walks straight -> spline -> bezier -> straight)
- [x] 1.4 Verify the extracted functions leave the interactive paths working: run the existing headless probes (`tools/probe_agent_api.py`, `tools/probe_pattern_validity.py`, `tools/probe_model_api.py`) and confirm nothing regressed (`model api check: OK`, `0 unexpected result(s)`, the delete regression returns `FINISHED`, and the agent probe is at 70 checks / 0 failures)

## 2. Surface plumbing for the new groups

- [x] 2.1 Create the `patterns`, `sewings`, `generators` and `components` submodules and publish them with the package; verify `import qyapi.patterns` reaches the same module as the package member, in a `-b` session
- [x] 2.2 Add the shared name resolution and refusal helpers (project, panel, edge by index or label, fabric) and verify an unknown name is refused with the names that exist (`_address.py`; the probe checks an unknown panel, an unknown edge label, an unknown fabric and an unknown component id)
- [x] 2.3 Extend the text index and the help topics for the new groups, and verify every public entry point appears in the index and in the shipped reference file (the probe compares the index against `docs/agent-api.md`: 0 missing)

## 3. Patterns

- [x] 3.1 Implement `create` (points in millimetres, closed counter-clockwise loop, optional name, granularity and fabric) and verify a four-point panel is meshed and measures one metre per 1000 millimetres (the probe's collar is 4 vertices / 4 edges / 258 mesh vertices at 10 mm; the millimetre-to-metre factor is the mesh pipeline's own `edge_points /= 1000`, which the world bounds of the test scene agree with)
- [x] 3.2 Implement the suffixed-name rule and verify a taken name returns both the requested and the final name (`collar` -> `collar.001`)
- [x] 3.3 Implement `get` (summary, edge table with index, label, kind, endpoints, handles, spline points and length) and verify every edge appears once in outline order
- [x] 3.4 Implement `points` as a separate call and verify the coordinates match the mesh within the pattern-to-metre scale
- [x] 3.5 Implement the per-panel sewing list on the shared edge-to-sewing index and verify it equals the project's sewings filtered by that panel (one builder for both, so they cannot disagree; the probe compares the indexes)
- [x] 3.6 Implement the vertex edits (set a vertex, add one by splitting an edge, remove one by merging its two edges) and verify the outline and the mesh both follow, that a crossing or degenerate result is refused, and that the refused value is put back (split 4->5 vertices and edges, merge back to 4/4; a crossing handle change is refused and the handle reads back at its old value)
- [x] 3.7 Implement the handle and spline point edits and verify an edge can be turned into a Bezier and into a spline and back to a straight line (kinds: straight, spline, bezier, straight)
- [x] 3.8 Implement the internal line edits and verify adding and removing one changes the panel's mesh (258 -> 254 -> 258 vertices)
- [x] 3.9 Implement the instance chain rule for edits and verify a panel with a mirror copy receives the same local geometry in both members and reports the chain (the probe edits the source and reads the same `p0` from the copy)
- [x] 3.10 Implement placement (anchor in millimetres, rotation, grain direction, collision layer, mirror in place) and verify the panel moves and reports its new placement
- [x] 3.11 Implement `copy` (instance or mirror at an anchor) on top of the extracted function and verify the copy is linked into the chain and both directions of the chain resolve (also verifies a copied Bezier edge keeps its kind)
- [x] 3.12 Implement `remove` and verify it reports the removed names and the sewings that went with them without asking, and that a panel a generator owns is refused with a pointer to detach or to the generator's remove
- [x] 3.13 Implement the validation used by every write (crossing outline, vertices closer than the mesh tolerance, non-positive granularity, unknown name or fabric) and verify each refusal leaves the scene untouched and carries a next action
- [x] 3.14 Implement the fabric name resolution (no name means the project default) and verify an unknown fabric is refused with the names the project has, and that no read path calls the writing `fabric` getter

## 4. Sewings

- [x] 4.1 Implement `sew(edge_a, edge_b, flip=False, color=None)` with edges addressed by index or label, forwarding the flag to the add-on's own `add_sewing1to1`, and verify both settings produce a seam and that the sides it recorded are reported back (forward the logic, derive nothing - the flag off records both sides at 0.0 -> 1.0 without a flip, the flag on records the second side at 1.0 -> 0.0 with the flip; measured separately on a pair of test panels at 11 and 9 stitches before wiring it in)
- [x] 4.2 Implement `sew_at` from a position between 0 and 1 on each edge through the same sewing, and verify it produces a seam for those points (13 stitches for the positions used)
- [x] 4.3 Implement the colour rule (given colour, otherwise a random one) and verify both paths land (a seam with no colour comes back with the add-on's own random saturated colour, `set_color` returns exactly the colour given)
- [x] 4.4 Implement `list`, the per-panel list and `remove`, and verify the two lists agree and a removed seam disappears from both
- [x] 4.5 Verify a refused seam reports `last_sewing_error`'s reason instead of a generic failure (observed while wiring this: a failing call reported the underlying `'Section' object has no attribute 'section'` rather than "sewing overlap!". A crafted overlapping pair was not built - the section machinery's own errors are what reach the caller)
- [x] 4.6 Verify a seam keeps its edges, positions and direction flag through a generator rebuild that keeps the edge list (three seams on the collar survive two parameter changes, both reporting `remapped: 0, dropped_sewings: 0`)

## 5. Generators, components and fabric

- [x] 5.1 Implement `components.list` and `components.info` and verify every built-in component appears with its schema and source, and an unknown id is refused with the ids that exist (8 components today, including a `gc_pencil_skirt` added by the other workstream)
- [x] 5.2 Implement `components.build` (outlines in millimetres, edge labels, the outline check) and verify it changes nothing in the scene and reports a crossing outline instead of returning it as usable
- [x] 5.3 Implement `components.reload` and verify a broken user component is reported while the others stay usable (reload reports 8 loaded and no errors with no user folder configured)
- [x] 5.4 Implement `generators.list` and `generators.get` (component, parameter table, output slots) and verify the parameters carry key, label, unit, range and value
- [x] 5.5 Implement `generators.create` and verify the panels are built, named in the result, and that an unknown parameter is refused while a value outside its range is clamped and reported (99.0 comes back as 5.0, the schema's maximum)
- [x] 5.6 Implement `set_params` as one call with one rebuild and verify the report carries the in-place, rebuilt, created, removed, remapped, dropped and invalid counts (`in_place: 2` for a two-panel generator)
- [x] 5.7 Implement the carried-over simulation flag in the rebuild report and verify the two cases: a rebuild after a run reports carried positions and leaves the panels off their rest pose, a rebuild before any run reports nothing to carry (`untouched` / `simulation_carried: false` before a run; `simulated` / `true` after one, with the seams intact)
- [x] 5.8 Implement `detach` and `remove` and verify detach keeps the panels as ordinary ones and remove takes the group and its sewings with it
- [x] 5.9 Verify a generated panel is readable and editable through the surface and reports that it comes from a generator, while the interactive lock still refuses the same edit through an operator (the surface half is verified; the operator lock is the other change's guard and its click-through needs a viewport)

## 6. Documentation

- [x] 6.1 Document the new groups in the module and verify a client that can only run Python reaches every entry point from the module itself
- [x] 6.2 Extend the shipped reference file and verify every entry point in it matches the text index
- [x] 6.3 Write the worked example (create a collar, sew it to the torso with a direction, change the torso's parameters, settle the result with a few simulation frames) and verify it runs end to end as written (the probe walks exactly those steps; the code block itself is prose, not executed verbatim)
- [x] 6.4 State the units and the coordinate spaces for the new calls (millimetres for panel space and anchors, metres for the mesh and the world), the naming and suffix rule, the instance chain rule, the undo granularity, and the fact that a rebuild can rewrite an edited generated panel (a `help("panels")` topic and a section of the reference file)

## 7. Verification

- [x] 7.1 Extend `tools/probe_agent_api.py` with a pattern section covering every call above and run it headless against the test scene; verify zero failures (70 checks, 0 failures)
- [x] 7.2 Run the acceptance scenario from the proposal as one script: build a generator, create a collar, sew it, change a parameter, settle with a few frames, and read both panels and the seams back; verify the seam survives the rebuild and the report says the simulation result was carried over (the collar moves 109.9 mm in four substeps, the seams survive both rebuilds, `simulation_carried: true`)
- [x] 7.3 Run `openspec validate agent-pattern-api --strict` and fix everything it reports

## 8. Notes from implementation

- `add_sewing1to1` was the two-flag form of a one-to-one sewing, orphaned when
  the operators moved to the click-based sewing, and broken in that state
  (`'Section' object has no attribute 'section'`). The maintainer rewrote it as
  the single-`reverse` form during this change; both directions were measured
  afterwards, so `qyapi.sewings.sew` forwards to it. `sew_at` still goes through
  `add_sewing1to1_from_points`, because it takes positions.
- Reading a seam's stitch count runs the add-on's own
  `calc_all_sewings_sections()`. Linking a subset raises "Sewing overlap!!!" for
  a valid seam, because the section link ids still point into the previous run;
  the whole-list call is the sequence the editor and the simulation use.
- `patterns.py` defines `list()`, which shadows the builtin inside that module.
  The one place that needed the builtin builds its pairs by hand now; a new call
  in that module must not reach for `list(...)`.
- Still needs a session with a viewport: the three interactive paths re-pointed
  in section 1 (the copy operator, the internal line pen, the curve write) and
  the operator half of 5.9.
