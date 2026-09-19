## Why

The pattern editor can draw an outline and move what it drew, but it cannot do
the edits a pattern maker performs while drafting: split an edge into equal
parts, cut an edge at a measured distance, round a corner, extend a seam
allowance by an arc, place a rectangle or a circle, turn an internal line into
a real outline, space internal lines, fold a pleat, or sew one long edge to
several short ones. Without those commands the add-on can only consume panels
that were drafted elsewhere.

## What Changes

- Edge commands: subdivide an edge or an edge chain into N equal parts or into
  segments of a target length; fillet a vertex into two points joined by an arc;
  extend an edge by an arc whose sweep follows the neighbouring edges; create
  and edit an arc as a first-class curve (three-point and centre/radius/sweep).
- Panel primitives: rectangle and circle/annulus generators in the panel
  library, with parameter schemas and preview, reusing the existing generator
  pipeline so a placed primitive stays parametric until it is detached.
- Internal lines: convert an internal line into an outline (splitting the
  panel) and a run of outline edges into an internal line; create a run of
  internal lines spaced by a distance; allow an internal line to be a sewing
  target.
- Pleat commands on an existing panel: fold pleats along marked internal lines
  (knife and box) and sewn pleats that pair the marked internal lines with a
  seam, so a skirt or a cuff can be made from a flat panel in place.
- Many-to-many sewing: one side of a seam may consist of several edge spans and
  the other side may consist of several others; the two sides are matched by
  proportional section mapping, extending the length-ratio split the section
  linker already performs. A seam stays one object with N sides.
- Copy options: flip an existing panel in place, copy with internal lines
  included, and copy carrying the sewings that lie entirely inside the copied
  selection (the double-layer copy).
- Expose every command through `qyapi` and document it in `docs/agent-api.md`.

## Capabilities

### New Capabilities

- `pattern-edge-tools`: dividing an edge or edge chain into parts (equal count
  or target length), filleting a vertex into two points, extending an edge by
  an arc that follows its neighbours, and creating/editing arc segments.
- `pattern-primitive-generators`: rectangle and circle/annulus panel generators
  in the panel library, with parameters, preview and the same
  rebuild/sewing-remap behaviour as the other components.
- `internal-line-tools`: converting between internal lines and outlines,
  spacing a run of internal lines by a distance, and using an internal line as
  a sewing side.
- `pattern-pleat-commands`: folding pleats along marked internal lines and
  sewing a pleat shut, applied to an existing panel.
- `sewing-many-to-many`: a sewing with more than two sides and several edge
  spans per side, matched by proportional section mapping, including its UI,
  its stitch generation and its behaviour when a side's edges change.
- `pattern-copy-options`: flipping a panel in place, copying internal lines,
  and copying the sewings contained in a copied selection.

### Modified Capabilities

- `agent-sewing-control`: a seam's sides are reported as ordered span lists
  rather than one edge each, and the report gains the unmatched remainder, so
  the existing read requirement changes.

## Impact

- Model: `Qianyi/model/pattern.py` (edge splitting helpers, arc edges,
  duplicated-panel construction), `Qianyi/model/geometry.py` and
  `Qianyi/model/section.py` (arc edges and split sections),
  `Qianyi/model/sewing.py` (N sides and proportional section matching),
  `Qianyi/model/internal_line.py` (outline conversion), and
  `Qianyi/model/qianyi_project.py` (sewing-aware copy).
- Operators and tools: `Qianyi/operators/_2d_*.py` (new edge commands,
  pleat commands, copy options), `Qianyi/declarations.py`,
  `Qianyi/keymaps.py`, and `Qianyi/workspacetools/`.
- Library: `Qianyi/panellib/components/` (rectangle, circle) and
  `Qianyi/generators.py` (preview and rebuild for a primitive).
- Script surface: `Qianyi/qyapi/patterns.py`, `Qianyi/qyapi/sewings.py`,
  `Qianyi/qyapi/components.py`, and `docs/agent-api.md`.
- Engine: no engine change is required. A many-to-many seam is decomposed into
  the existing two-pattern stitch payload, and every other command is a
  2D-geometry edit that ends in the same `sample_points` call.
