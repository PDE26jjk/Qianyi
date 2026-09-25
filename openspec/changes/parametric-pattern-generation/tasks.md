## 1. Component library (Blender-free)

- [x] 1.1 Create the library package layout (curve primitives, pattern/edge specification, component protocol, helpers) and verify it imports in a plain Python session that has only numpy installed
- [x] 1.2 Implement the curve primitives (line, quadratic/cubic curve, arc, point list) and their reduction to a straight edge, a cubic Bezier edge or a sequence of straight edges; verify with a unit test that each primitive's emitted shape matches its source within tolerance
- [x] 1.3 Implement the pattern and edge specification, including the closed counter-clockwise loop validation, automatic positional names for unlabelled edges, rejection of duplicate labels, and the sewability flag; verify with unit tests for each rule
- [x] 1.4 Implement the deterministic decorative-run helper (seed, amplitude, wavelength, sample count) and verify that two runs with the same seed are identical and that runs are marked not sewable by default
- [x] 1.5 Add the component protocol (schema, build) and verify that a component can be generated twice with identical results and that no component module imports Blender
- [x] 1.6 Write two example components (a square pattern with width/height, and a waistband) and verify their unit tests cover area, closure and label assignment
- [x] 1.7 Add the local-frame stability check and verify that changing a length or width parameter keeps the anchoring region of a pattern within the configured tolerance of its previous position

## 2. Generator model and rebuild

- [ ] 2.1 Add the generator model (component id, parameter block, slot outputs) plus the single field that links a pattern to its generator; verify a project can save and reload a generator with its patterns (link logic verified by clearing the in-memory uuid map and re-resolving; the .blend round trip still needs a manual check, see the notes at the end of this file)
- [x] 2.2 Implement generator creation from a component and verify the project receives one pattern per slot with the slot's name
- [x] 2.3 Implement the rebuild entry point (build, then write patterns by slot, reusing the existing pattern per slot) and verify that regenerating does not create duplicate patterns
- [x] 2.4 Implement the in-place write path (rewriting existing vertices, handles and spline points when a pattern's edge list is unchanged) and verify edge identities are unchanged after a shape-only parameter change
- [x] 2.5 Implement the rebuild fallback for a changed edge list and verify the pattern is rebuilt without duplicating slots or losing its placement, fabric and collision settings
- [x] 2.6 Wire parameter changes to the rebuild entry point and verify that editing a parameter updates the patterns with no further user action
- [x] 2.7 Report invalid generator state (unknown component, invalid parameters) without touching the existing patterns and verify the user sees an error
- [ ] 2.8 Add the generator UI panel (generator list, schema-driven parameter widgets, detach action) and verify parameters are editable and the widget set follows the component schema (implemented; the visual pass still has to happen in a normal Blender session)
- [x] 2.9 Implement group lifecycle: deleting any generated pattern deletes the whole group, and detaching turns the whole group into ordinary patterns; verify both with a scripted scene

## 9. Follow-ups found while implementing

- [ ] 9.1 Verify the .blend round trip in an interactive session (a factory-startup background session drops the project datablock before the add-on is registered, so the reload half of 2.1 cannot be checked headlessly)
- [x] 9.2 Decide how the library panel shows a component's thumbnail, and add it once decided (numpy-rasterised outline of the component's first generation, shown through a Blender image preview)

## 3. Locking of generated patterns

- [x] 3.1 Audit the 2D editing operators and list every path that can change pattern geometry; deliver the list as the input for 3.2 (guarded: add vertex, add spline point, edge mode move, element delete in edge mode, internal line pen, pattern scale; left free: pattern pen and curve import, which create new patterns)
- [x] 3.2 Add the guard to the geometry-editing operators (vertex add/move, spline points, edge move, internal lines, scale) and verify each refuses a generated pattern with a visible message while leaving geometry unchanged (guards are in place and the lock message was verified headless; the interactive click-through still needs a session with a viewport)
- [x] 3.3 Verify the operations that must stay available on a generated pattern: sewing, simulation, fabric and collision settings, grain direction, 2D placement, mirror and instance copies, and deletion (no guard was added to those paths: move, rotate, copy instance, sewing, material and simulation code)
- [x] 3.4 Verify that a detached pattern accepts every editing operation again (locking resolves through the generator link, which detach clears, so a detached pattern has no lock at all)

## 4. Sewing remap

- [x] 4.1 Implement the pre-rebuild snapshot (edge identity, label, sampled boundary points per output pattern) and verify it is taken before any pattern is written (taken at the top of the rebuild, for every member of each instance chain)
- [x] 4.2 Implement matching by label and verify a rebuild that reorders edges but keeps labels reconnects the sewings to the labelled edges (a labelled edge that changes shape keeps its sewing: verified with a sewing on the square's top edge across a bow change)
- [x] 4.3 Implement the geometric fallback (nearest boundary point on the rebuilt pattern) and verify a rebuild that removes a label still reconnects to the nearest edge (nearest-edge match over the previous edge's sample points; the fallback runs whenever the label is absent)
- [x] 4.4 Implement re-anchoring (replace the edge identities, keep positions) and verify sewings on an in-place rebuild are byte-identical afterwards (an in-place rebuild reports zero remapped sewings, so the identities are untouched)
- [x] 4.5 Implement removal of sewings whose edge has no match and verify no invalid or suspended sewing state remains (a snapshot entry with no counterpart drops its sewing: 1 dropped, 0 sewings left)
- [x] 4.6 Scope the remap to the patterns of the rebuilt generator and verify an unrelated sewing elsewhere in the project is untouched (only edge identities present in the snapshot are considered, so the far side of a sewing on another pattern keeps its identity)

## 5. Component hook prototype

- [x] 5.1 Write a component whose own parameter changes its edge list (for example an optional opening on one edge) so the hook has a real caller (the notched pattern: turning the notch on replaces the top edge with three edges)
- [x] 5.2 Implement the hook call site with the three outcomes (default matching, edge mapping, handled) and verify each outcome with a scripted rebuild (verified with a temporary hook: it is called with the old and new edge lists, its handled answer skips the default remap, and an edge map is used instead of matching)
- [x] 5.3 Evaluate the hook's argument shape against 5.1 and record the final signature in design.md, updating the Open Questions section

## 6. Instances and mirror copies

- [x] 6.1 Include instance copies in the rebuild so a mirrored copy follows its source, and verify the copy keeps its mirrored placement after a parameter change (a rebuild now writes and remeshes every member of the instance chain; verified that a copy receives the geometry and matches its source)
- [x] 6.2 Include instance copies in the remap and verify sewings that reference copy edges are re-anchored or removed (the snapshot and the remap both walk the instance chain; a sewing on a copy survived a rebuild of its source with its edge identity intact)

## 7. Integration verification

- [x] 7.1 Build an end-to-end headless Blender script (generate a multi-pattern component, sew it to a hand-drawn pattern, run the simulation) and verify the scene simulates without errors (verified by the maintainer in a live session; simulation was run and accepted)
- [x] 7.2 Verify that a shape-only parameter change keeps every sewing on the generated patterns, and that a topology-changing parameter change matches or removes them as specified (sewing survival across a shape change is covered by the scripted scene; the maintainer's run confirmed the end-to-end path)
- [ ] 7.3 Export the generated scene through the scene-capture path and verify the engine harness can load and run it

## 8. Validation

- [x] 8.1 Run `openspec validate parametric-pattern-generation --strict` and fix any reported issue (valid; the duplicate task id it reported earlier was fixed)
- [x] 8.2 Review the delivered behaviour against each spec scenario and record any scenario that is not yet covered by a check (see the coverage table below)

### Scenario coverage (8.2)

Checked headlessly, in the library tests or in the scripted Blender scene:

| Spec scenario | State |
| --- | --- |
| library: repeated generation, import without Blender, positional labels, duplicate labels rejected, straight/Bezier exact, arc tolerance, point lists, same seed, reference point stability, dependency budget | covered by the 24 library tests |
| library: decorative edges are not sewable | flag and landing covered; the sewing tools are not filtered yet - open |
| generator: creates patterns, parameter change rebuilds, in-place keeps edge identity, delete one deletes the group, detach keeps patterns, invalid parameters leave patterns untouched, outline refused before the mesh, copies follow their source | covered by the scripted scene |
| generator: a component with more slots adds only new patterns | no component with a variable slot count exists yet - open |
| generator: generated pattern sewn to a hand-drawn pattern | covered by the user's simulation run |
| locking: vertex edit refused, copy of a generated pattern refused, detached pattern editable | guard verified as a function; the click-through needs a viewport - open |
| locking: sewing allowed | covered (a sewing on a generated pattern was built and survived a rebuild) |
| locking: mirroring allowed | the instance chain is created and follows its source; the click-through needs a viewport - open |
| browser: thumbnails and names, filters, empty result, details, add | thumbnail rendering, filtering logic and the add path are covered; the visual pass needs a viewport - open |
| remap: storage unchanged, shape-only untouched, label match, unmatched removed, scope, hook mapping, hook handled, instance copy | covered by the scripted scene |
| remap: geometry fallback after a reordered or split edge | implemented and reachable, but no built-in component reorders or splits an edge under a sewing yet - open |

## 10. Library browser and outline checking

- [x] 10.1 Generate a thumbnail per component (numpy rasterisation of the pattern outlines) and verify a thumbnail is produced for every built-in component
- [x] 10.2 Draw the library as a grid of thumbnail + name cells with several cells per row, and verify the grid lists every component
- [x] 10.3 Add a free-text filter and a category filter, and verify both narrow the grid and that an empty result is reported
- [x] 10.4 Add selection with a detail area (name, category, description, parameter table) and an action that adds the selected component to the project
- [x] 10.5 Check every pattern with the editor's own outline test before writing it, and verify that an impossible parameter (for example a negative height) leaves the patterns unchanged and reports an error instead of rebuilding
- [x] 10.6 Keep numeric work vectorised with numpy and comment every remaining loop with why numpy cannot be used; verify the library tests still pass after the change

## 11. User components, cost and follow-ups

- [x] 11.1 Add the component folders to the add-on preferences and verify the library still works with no folder configured
- [x] 11.2 Reload user components from the configured folders, re-reading each file from source, and verify an edited value is picked up on reload (111.0 -> 222.0) while a failing file is reported and the others stay usable
- [x] 11.3 Label each library entry with its origin and list the files that failed to load
- [x] 11.4 Measure a large component and record the cost: 1003 edges build in 9.4 ms and land in 2.3 ms, a first generation takes 1.9 s (mesh pipeline) and a parameter change 0.45 s, of which the generator's own write is 10-20 ms
- [x] 11.5 Skip the rebuild while a parameter is being dragged: a heavy generator (more than 300 edges) rebuilds 0.2 s after the last change, and a scripted session keeps rebuilding immediately
- [x] 11.6 Index the sewings once per rebuild instead of scanning them per pattern, and verify the scripted scene still passes
