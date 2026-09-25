## 1. The projects group

- [x] 1.1 Implement `projects.list()` and verify it reports every project with the name it is addressed by, whether it is active, and its pattern, sewing, fabric and generator counts (an empty scene reports `{"projects": [], "active": None}`; the test scene reports its project with its counts)
- [x] 1.2 Implement `projects.create(name=None, activate=True)` - the node tree, the identities of the project and its default fabric, both names and the active index - and verify that a pattern created straight afterwards needs no further setup in a scene that started empty (the blank section creates a project and then a pattern with its mesh, in one session)
- [x] 1.3 Verify a created project carries the name it is addressed by, that the editor's project list draws that same name (`QY_UL_ProjectList.draw_item` reads the property), and that the node tree's datablock key is only reported as a diagnostic (the created name equals the datablock key here, and the answer reports the key under `datablock`)
- [x] 1.4 Implement `projects.active()` and `projects.activate(name)` and verify that a call naming no project works on the activated one, and that activating still works when the scene holds node trees that are not projects (the test scene holds two `ShaderNodeTree`s alongside the project)
- [x] 1.5 Implement `projects.rename(name, new_name)` and verify both names read back as the new one and the old name no longer resolves (the old name is refused, and a name already taken is refused rather than suffixed)
- [x] 1.6 Implement `projects.remove(name)` and verify it reports the patterns and sewings that went with it (and, as the notes below record, that the patterns' mesh objects go with them)
- [x] 1.7 Verify the empty-scene path: `projects.list()` returns nothing, a pattern call before any project is refused with the call that makes one, and a project created after that makes the same pattern call succeed
- [x] 1.8 Verify the identity work is what makes it work: create a project with the node tree call alone and confirm the pattern call still fails, so a future change cannot quietly drop the identity step (the blank section keeps this check: `node_tree_alone_error: AssertionError`)

## 2. The crossing policy

- [x] 2.1 Add `allow_crossing=False` to `create`, `set_point`, `add_point` and `remove_point` and verify the default refuses a crossing outline before anything is written (`moving that point would cross itself near (0.000, 33.333)`, and the pattern keeps its validity)
- [x] 2.2 Add the same argument to `set_handle`, `add_spline_point` and `remove_spline_point` and verify that with the flag off a crossing edit is still put back, while with the flag on it is applied (with the flag on a handle edit lands, the outline reads invalid, the mesh is stale and the answer says `allowed_crossing`; with it off the test scene still shows the handle put back at its old value)
- [x] 2.3 Verify one call does not decide for the next: a write with the flag on followed by a write without it refuses a crossing outline again
- [x] 2.4 Verify the scene's Check Self-Intersection switch is never read or written by the surface (compare it around a set of writes with and without the flag: unchanged)
- [x] 2.5 Add the crossing reporting to every geometry answer: `outline_validity`, the crossing point when known, and `mesh_stale` when the mesh was not rebuilt
- [x] 2.6 Verify a crossing outline is never handed to the mesh sampler: with the flag on, the pattern keeps the mesh it had (166 vertices before and after) and the answer says it is stale; a pattern created crossing has no mesh object at all
- [x] 2.7 Verify a simulation still refuses a crossing pattern by name, and that `validate()` still reports it as a read without raising
- [x] 2.8 Verify the outline can be fixed: a later write without the flag makes the mesh rebuild (valid, not stale, 166 vertices) and a simulation then prepares on it
- [x] 2.9 Add the pattern names and the stale-mesh flag to the generator rebuild report, and verify a parameter change that leaves a pattern crossing is still applied, still counted, and now names the affected patterns (`notch_depth` 10 -> 200 on a 100 mm pattern: `invalid_patterns: 1`, `invalid_pattern_names: ["notched"]`, `stale_meshes: ["notched"]`)
- [x] 2.10 Verify a generator rebuild takes no crossing argument and gains no refusal: set a parameter that leaves a pattern crossing and confirm the call succeeds exactly as it did before this change (`takes_flag: False`, the rebuild applies and reports)

## 3. Documentation

- [x] 3.1 Document the `projects` group in the module and in the shipped reference file, including the two-names rule and that an index is not an address
- [x] 3.2 Document `allow_crossing` per call: what it relaxes, what it does not, and the habit of validating before starting a simulation
- [x] 3.3 Extend the worked example to start from a blank file: create a project, build a collar through a crossing intermediate state, fix the outline, then sew and simulate

## 4. Verification

- [x] 4.1 Extend `tools/probe_agent_api.py` with a blank-scene section (no scene file): create a project, build a pattern, list, rename, activate a second project, remove one - and verify zero failures (`--blank`: 13 checks, 0 failures)
- [x] 4.2 Run the existing probe against the test scene and verify the earlier behaviour is unchanged: 70 checks, 0 failures, with the scene's switch untouched
- [x] 4.3 Run `openspec validate agent-project-and-crossing --strict` and fix everything it reports

## 5. Notes from implementation

- `projects.remove` has to take the patterns out through the model layer before the
  node tree goes. A pattern's mesh object is a scene object, not part of the tree,
  so removing the tree alone left an object whose `pattern_uuid` no longer
  resolved - and the next `sim.prepare()` then failed inside
  `ObjectSimulationProperties.pattern` with `Can not find pattern_uuid`. Routing
  through `remove_patterns` deletes those meshes, as the ordinary pattern removal
  already did.
- An ambiguous pattern name is now refused. A generator names its patterns after the
  component's slots, so a slot can collide with a hand-made pattern: the probe hit
  exactly that (a hand-made `square` next to a `square` slot) and the surface
  answered with the first match. `pattern_or_refuse` now reports how many patterns
  carry the name and refuses rather than guessing.
- `QianyiProject` inherits `ModelData.name`, which shadows the node tree's own
  datablock name. The editor's project list draws that same property, so the UI
  and the surface agree on the name; the datablock key is reported under
  `datablock` for a caller that has to find the tree in `bpy.data`, and is not an
  address.
- Still needs a session with a viewport: nothing in this change - the seven
  writes, the projects group and the generator report are all exercised headless.
