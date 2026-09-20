# Qianyi

Qianyi (牵衣) is a Blender add-on for garment design and cloth simulation. It
gives a pattern maker a 2D pattern window, a sewing editor, a parameterised
panel library and a live simulation of the garment on a body, and it drives a
CUDA physics engine for the cloth.

Chinese version of this file: [README.zh-CN.md](README.zh-CN.md).

## A release ships two repositories together

| Part | What it is | Where |
| --- | --- | --- |
| **Qianyi** (this repository) | The Blender add-on. Blender 4.3+, GPL-3.0-or-later. | <https://github.com/PDE26jjk/Qianyi> |
| **Qianyi_DP** | The simulation and geometry engine: C++20 + CUDA + pybind11, built into a Python extension module for Blender's interpreter. | <https://github.com/PDE26jjk/Qianyi_DP> |

The add-on cannot simulate anything on its own: it builds the mesh payload and
the seam list, and the engine solves them. A release therefore pins an add-on
version and an engine build together, and both are installed from the same
release.

## Requirements

- Blender 4.3 or newer.
- An NVIDIA GPU with a working CUDA driver. The add-on cannot do its work
  without one: the engine is a CUDA program, and it runs not only the simulation
  but also the panel meshing (point sampling and triangulation), the outline
  self-intersection tests and the sewing helper. A machine without a
  CUDA-capable device cannot mesh or simulate a panel at all.
- The `Qianyi_DP` module built for the same Python ABI as the Blender you run,
  importable by Blender's Python interpreter.
- No third-party Python packages: the add-on uses only what Blender ships,
  numpy included.

## What the add-on does today

- **Projects** are Blender node trees, so a `.blend` file holds several
  projects, each with its own patterns, sewings and fabrics.
- **Patterns** are drawn with a pen, edited as straight edges, cubic Beziers or
  interpolating splines, and can carry internal lines (open runs, closed loops
  and holes) that are intersected with the outline.
- **Panel library**: 26 built-in parameterised components (rectangle, notched
  panel, pleated panel, waistband and the GarmentCode garment presets), plus
  user component folders that are re-scanned on reload.
- **Sewings** join one edge span of one panel to one edge span of another, with
  a direction taken from the click, a colour, and the ability to span several
  consecutive edges.
- **Simulation**: pick a solver, edit its parameter block (including unknown
  keys), run it freely or with the animation timeline, record and play a frame
  cache, and export the cache as a PC2 Mesh Cache modifier.
- **A script surface** (`qyapi`) that can build and drive all of the above from
  a plain Python statement, with one undo step per write.

## Roadmap

The list below is where the add-on stands against a production garment-design
tool, by category. `[x]` is shipped, `[ ]` is not. Items marked with a change
name are specified in `openspec/changes/<name>/`.

### 1. Panel states and physical behaviour

- [x] Collider objects participate in the simulation with their own collision
  layer, and can be re-read every frame.
- [ ] Per-panel state: simulate / excluded from the solve / frozen in place /
  stiffened — `panel-states-and-display`.
- [ ] Per-panel stiffness multiplier as an override of the shared fabric —
  `panel-states-and-display`.
- [ ] Bake the current drape into the rest shape (plasticity freeze), with the
  engine's rest-shape work — the engine side is `cloth-plasticity` in
  Qianyi_DP; the add-on exposes it once that ships.
- [ ] A genuinely rigid panel (rigid-body behaviour rather than a stiffness
  multiplier).
- [ ] Bonding two panels into one continuous piece without a seam
  (hot-melt / seamless construction).
- [ ] Skiving: thickness tapered along an edge (leather, footwear, heavy
  fabrics).

### 2. Display and viewport

- [x] Pattern window drawing: outline, internal lines, spline points, seam
  lines, preselection, grain direction and the outline-validity marker.
- [x] Display modes for the pattern window: solid, wireframe, mesh, stress,
  debug — `panel-states-and-display`.
- [x] Stress and debug vertex colours in the 3D viewport, drawn as an overlay
  over the material Blender renders — `panel-states-and-display`.
- [x] Seam lines drawn in the 3D viewport between the paired stitch vertices,
  with depth — `panel-states-and-display`.
- [x] The avatar silhouette projected into the pattern window as an alignment
  guide (a project collection, projected 1:1 with its mesh edges, cached) —
  `panel-states-and-display`.
- [ ] Anti-aliased points and lines, and a line-width control that survives a
  redraw.
- [ ] Fabric texture and UV display on the simulated garment.

### 3. Pattern geometry tools

- [x] Pen drawing, inserting a vertex or a spline point, move, rotate, scale,
  box select and delete.
- [x] Parametric rectangle (the `square` component), notched panel, pleated
  panel and waistband; each rebuilds in place with its sewings remapped.
- [ ] Divide an edge or a chain into N equal parts by arc length, or at a
  target length and cut count — `pattern-editing-toolkit`.
- [ ] Round, chamfer or hollow a corner — `pattern-editing-toolkit`.
- [ ] Open a fan at a pivot: rotate one half of the panel and fill the sector
  that opens — `pattern-editing-toolkit`.
- [ ] Drag a curve into the shape the pointer describes, written back as points
  (straight stays straight, exact arcs stay Bezier, the rest becomes a spline)
  — `pattern-editing-toolkit`.
- [ ] A generic circle and annulus generator — `pattern-editing-toolkit`.
- [ ] Copy and paste of pattern elements.
- [ ] Measuring tools: distances and angles between points, edges and the body.

### 4. Internal lines

- [x] Draw, delete and re-shape internal lines, including closed loops as
  holes, with the outline intersection and the outside part marked.
- [ ] Cut a panel along an internal line into two panels —
  `pattern-editing-toolkit`.
- [ ] Turn a run of outline edges into an internal line —
  `pattern-editing-toolkit`.
- [ ] Repeat internal lines at a signed distance, with the ends clipped,
  projected onto the outline or kept as they are — `pattern-editing-toolkit`.
- [ ] Use an internal line as a sewing side (a dart sewn shut) —
  `pattern-editing-toolkit`.

### 5. Pleats and garment-specific commands

- [x] A parameterised pleated panel component (a rectangle with a folded edge).
- [ ] Fold pleats (knife and box) along marked lines on an existing panel —
  waits for the engine to carry an angle on an internal line.
- [ ] Sewn pleats that create the seams holding them — waits for the same
  engine support.
- [ ] Gathers and ruffles (sew a long edge to a short one and let the material
  bunch).
- [ ] Darts as one command (mark, fold and close a dart).

### 6. Sewing

- [x] One-to-one seams with free start and end positions, spanning several
  consecutive edges, with a colour and a direction taken from the click.
- [x] Seams declared by a generator, remapped by edge label and geometry when
  the panel is rebuilt.
- [ ] Many-to-many seams: several drawn spans per side, matched by proportional
  section mapping — `pattern-editing-toolkit`.
- [ ] Per-seam stitch parameters (strength, stitch count) instead of the single
  global sewing stiffness.
- [ ] Seam types other than a straight join: tape, binding and folded edges.

### 7. Panels, copies and instances

- [x] Instance copies with live linked editing, and mirror copies.
- [ ] Flip a panel in place (horizontal, vertical, through two points) —
  `pattern-editing-toolkit`.
- [ ] Copy with or without internal lines — `pattern-editing-toolkit`.
- [ ] Copy the seams contained in the copied selection (the double-layer copy),
  while an instance or mirror copy carries none — `pattern-editing-toolkit`.
- [ ] Mirror a panel or a group about a project axis, rather than about the
  panel's own anchor.
- [ ] Groups: named collections of panels that move and hide together.

### 8. Simulation controls and environment

- [x] Solver selection (PDNewton, and the experimental VBD / XPBD / Explicit),
  the full parameter block, custom key/value parameters, JSON import of a
  parameter file, and a per-scene "apply on start" switch.
- [x] Free simulation, simulation driven by the animation timeline, frame-cache
  recording and playback, and PC2 export through a Mesh Cache modifier.
- [x] Gravity, ground contact, collision layers and the pick-and-drag
  interaction in the 3D viewport.
- [x] A simulation HUD in the viewport: the run state, the solver and the frame
  count, and the real-time speed as simulated time over wall-clock time.
- [ ] Wind and air forces (needs engine support).
- [ ] Pressure / inflate for down jackets and other filled garments (needs
  engine support).
- [ ] Body management: a reusable avatar list, per-garment body binding and an
  undoable avatar swap.
- [ ] Measurement-driven sizing: a body measurement source that feeds the
  generator parameters (today every parameter is a number the caller supplies).

### 9. Mesh and topology

- [x] Panel meshes sampled from the boundary at the panel's granularity through
  the engine's constrained triangulation.
- [ ] Quad or quad-dominant panel meshes (needs engine support).
- [ ] Mesh density controls in the UI: a finer mesh near seams and edges, a
  coarser one inside a panel.

### 10. Load, save and interoperability

- [x] Everything lives in the `.blend` file, with undo and redo.
- [x] Marvelous Designer project import (`.zpac`).
- [x] Scene capture (`scene.json` + `scene.npz`) for reproducing a scene
  outside Blender.
- [ ] Pattern and seam export to an interchange format (OBJ, DXF, AAMA/ASTM,
  glTF or FBX) so a pattern can be drafted elsewhere.
- [ ] Fabric and pattern-library import/export (a shared material and component
  library rather than one per project).
- [ ] A documented capture -> replay -> compare round trip.

### 11. Scripting and automation

- [x] `qyapi`: projects, patterns, sewings, generators and simulation, with
  `help()`, `state()`, transactions and one undo step per write
  (see `docs/agent-api.md`).
- [x] A panel-component API that builds a panel without touching the scene, so
  a component can be written and checked before it is placed.
- [ ] A capture/replay comparison report for regression work.
- [ ] Optional: an MCP layer over `qyapi` for external agents.

### 12. Quality, tests and documentation

- [x] CPU-only unit tests for the panel library
  (`python Qianyi/panellib/tests/run_tests.py`, numpy only, no Blender).
- [x] Outline self-intersection checking, and the sewing direction and crossing
  probes recorded in the OpenSpec changes.
- [ ] Regression tests for the new pattern commands and display modes as they
  land.
- [ ] A release checklist naming which engine build each add-on version
  requires, and what is verified before shipping.
- [ ] Clean up the remaining placeholders: the tool-settings labels that still
  read `?????`, the two unimplemented operators declared as TODOs, and the
  right-click menu, which currently offers only move and copy-instance.

## Development

- Panel library tests, with no Blender and no engine:

  ```bash
  python Qianyi/panellib/tests/run_tests.py
  ```

- The design work is tracked with OpenSpec:

  ```bash
  openspec list
  openspec status --change panel-states-and-display
  openspec validate panel-states-and-display --strict
  ```

- Conventions: code comments and committed public files are written in
  English; numeric work uses numpy vector operations rather than Python loops;
  no third-party Python dependency is added; machine-specific paths and local
  build output never appear in committed files.

## Credits

- The editor's operator and gizmo structure follows
  [CAD_Sketcher](https://github.com/hlorus/CAD_Sketcher).
- The translation setup follows
  [MMD_Tools](https://github.com/MMD-Blender/blender_mmd_tools).
- The engine's triangle meshing uses
  [gDel2D](https://www.comp.nus.edu.sg/~tants/gdel3d.html), and its broad phase
  follows [ppf-contact-solver](https://github.com/st-tech/ppf-contact-solver).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
