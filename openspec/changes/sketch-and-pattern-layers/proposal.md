## Why

The geometry a pattern maker draws and the geometry the add-on computes from it
(sampled points, mesh, stitch walks, engine payload) live in the same object, and
an instance chain keeps one such object per copy, held in step by writing every
edit to every member by index. That is why one shape exists N times, why copies
can drift apart, and why every operator has to keep a set of cache flags correct
by hand.

## What Changes

- Add the **shape layer**: one authored shape per instance chain, holding the
  vertices, edges, handles, spline points and internal lines, the editor's own
  draw points, and the first section stage - the sections of every edge plus the
  pieces that crossings cut them into, with the inside/outside classification of
  an internal line.
- Leave the **piece layer** with identity, placement and derived data: name,
  anchor, rotation, mirror flag, grain direction, fabric, collision layer,
  granularity, simulation state and instance chain on one side; sampled points,
  mesh, stitch walks and the engine payload on the other.
- Replace the per-copy write convention with one contract: a topology edit
  writes the shape once and raises its revision; a consumer bakes a piece whose
  derived data was baked from an older revision.
- Make the section stage of a shape independent of a panel's granularity, so
  which pieces a shape consists of is a property of the shape alone.
- **BREAKING**: a copy no longer holds vector geometry of its own. Copying
  shares the shape; detaching gives one piece a private copy of it. Every place
  that reaches a panel's vertices or edges - operator, panel, script - goes
  through the shape now.
- **BREAKING**: a scene saved by an earlier build is read by adopting the vector
  collections a panel already stores into a private shape for that panel.

## Capabilities

### New Capabilities

- `pattern-layers`: the two layers of a panel, the single shape of an instance
  chain, the revision a shape change raises, the bake contract for derived data,
  detaching a piece from its chain, and the placement and simulation state that
  stay per piece.

### Modified Capabilities

- `agent-pattern-authoring`: the instance-chain rule changes from "an edit is
  written to every member" to "one shape, edited once, seen by every member",
  and a copy is stated to share its source's shape rather than duplicate it.

## Impact

- Model: the panel's own vertices, edges and internal lines move behind a shape
  object; the revision and the bake contract replace today's cache flags.
- Editing operators: every tool that changes topology writes the shape and stops
  there; the drift refusal and the per-member write loops disappear.
- Display and picking: the editor draws a shape's own draw points, and a picked
  element resolves to the shape element together with the piece it was picked
  on, because one shape can be on screen in several places.
- Sewing: a seam side names the piece it belongs to and the shape element it
  runs along; its stitch walk becomes derived data of that piece.
- Simulation bridge and generators: a prepare bakes every stale piece before
  exporting; a generator writes a shape and places the pieces it owns.
- Surfaces: the script surface and `docs/agent-api.md` name shapes and pieces
  separately; existing calls keep their names where the behavior is unchanged.
- Engine: unchanged - it still receives one mesh payload per piece.
