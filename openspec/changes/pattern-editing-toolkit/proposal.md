## Why

The pattern editor can draw an outline and move what it drew, but it cannot do
the edits a pattern maker performs while drafting: divide an edge into equal
parts or at measured distances, round or chamfer a corner, open a fan at a
pivot, place a rectangle or a circle, turn an internal line into a real outline,
space internal lines by distance, or sew one long edge to several short ones.
Without those commands the add-on can only consume patterns that were drafted
elsewhere.

## What Changes

- Shared curve rules: every command measures along arc length and writes its
  result back as points - straight pieces stay straight, exactly-representable
  curves keep their Bezier, everything else becomes a spline fitted within a
  project fitting tolerance - and a project merge threshold keeps
  near-coincident points from reaching the triangulation, which does not define
  a result below that scale.
- Edge commands: divide an edge or an edge chain into N equal parts by arc
  length, or by a target length with a cut count (default one, capped at what
  the selection holds, the last piece absorbing the remainder); round, chamfer
  or hollow a corner; open a fan at a pivot by rotating one half of the pattern
  and filling the sector that opens; drag a curve into the shape the pointer
  describes.
- Pattern primitives: rectangle and circle/annulus generators in the pattern
  library, with parameter schemas and preview, reusing the existing generator
  pipeline so a placed primitive stays parametric until it is detached.
- Internal lines: cut a pattern along an internal line that crosses the outline
  exactly twice (both halves join the source's instance chain, with an optional
  seam along the cut); convert a run of outline edges into an internal line;
  create a run of internal lines at a signed distance with the ends clipped,
  projected onto the outline or left as they are, de-looping each generated line
  so it is never left self-crossing; allow an internal line to be a sewing side.
- Many-to-many sewing: each side of a seam becomes a set of drawn spans, matched
  by the section linker's proportional mapping, with the tolerance calibrated by
  experiment. A seam stays one object, both of its sides stay on one pattern each,
  and the engine payload is unchanged.
- Copy options: flip an existing pattern in place, copy with internal lines
  included, and copy carrying the sewings that lie entirely inside the copied
  selection. An instance or mirror copy carries no seams.
- Keep the editor's mode-based structure, but remove its cost: picking a tool
  puts the editor into the mode that tool works in, and a selection survives a
  mode change (it is drawn dimmed while another mode is active). A unified
  selection model was considered and rejected - see `design.md`.
- Make the geometry commands act on the current selection and keep them
  re-runnable, so Blender's own **adjust last operation** pattern can change a
  parameter after the fact (part count, target length, corner radius, fan
  angle). The drawing tools - the pens, the sewing tool, box select, the 3D
  pick - are documented exceptions: they have no parameter to adjust.
- Expose every command through `qyapi` and document it in `docs/agent-api.md`.

Pleat commands are deliberately **not** in this change: folding an internal line
needs the engine to carry an angle on that line, and it does not do so yet.

## Capabilities

### New Capabilities

- `pattern-edge-tools`: measuring and dividing an edge or edge chain by arc
  length or by a target length, rounding/chamfering/hollowing a corner, opening
  a fan at a pivot, editing a curve by dragging it, and the shared rules that
  keep the written geometry fitted and above the merge threshold.
- `pattern-primitive-generators`: rectangle and circle/annulus pattern generators
  in the pattern library, with parameters, preview and the same rebuild/sewing
  remap behaviour as the other components.
- `internal-line-tools`: converting between internal lines and outlines, spacing
  a run of internal lines by a signed distance, and using an internal line as a
  sewing side.
- `sewing-many-to-many`: a seam whose two sides each hold a set of drawn spans,
  matched by proportional section mapping, including its UI, its stitch
  generation and its behaviour when a side's edges change.
- `pattern-copy-options`: flipping a pattern in place, copying internal lines, and
  copying the sewings contained in a copied selection.
- `pattern-tool-interaction`: how a tool relates to the editor's modes (a tool
  activates its own mode, a selection survives a mode change), what a command
  acts on (the selection, with hover only choosing it), and the contract that
  makes a command re-runnable from Blender's adjust-last-operation panel -
  including the derived work, such as remapping the sewings that a topology
  change moves.

### Modified Capabilities

- `agent-sewing-control`: a seam's sides are reported as ordered span sets
  rather than one edge each, and the report gains the unmatched remainder, so
  the existing read requirement changes.

## Impact

- Model: `Qianyi/model/pattern.py` (edge division, corner tools, the fan,
  duplicated-pattern construction), `Qianyi/model/geometry.py` (curve fitting and
  the merge threshold), `Qianyi/model/section.py` (split sections on refitted
  edges), `Qianyi/model/sewing.py` (span sets and proportional section
  matching), `Qianyi/model/internal_line.py` (outline conversion and offsets),
  and `Qianyi/model/qianyi_project.py` (sewing-aware copy).
- New shared utilities for arc-length sampling, curve fitting and offset loop
  removal, used by the model layer rather than by the operators.
- Operators and tools: `Qianyi/operators/_2d_*.py` (the new edge commands, copy
  options), `Qianyi/declarations.py`, `Qianyi/keymaps.py`, and
  `Qianyi/workspacetools/`.
- Library: `Qianyi/patternlib/components/` (rectangle, circle) and
  `Qianyi/generators.py` (preview and rebuild for a primitive).
- Script surface: `Qianyi/qyapi/patterns.py`, `Qianyi/qyapi/sewings.py`,
  `Qianyi/qyapi/components.py`, and `docs/agent-api.md`.
- Engine: no engine change is required. Every command is a 2D-geometry edit that
  ends in the same `sample_points` call, and a many-to-many seam is still one
  two-pattern stitch group.
