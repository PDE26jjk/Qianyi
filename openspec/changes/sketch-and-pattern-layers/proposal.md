## Why

The geometry a pattern maker draws and the geometry the add-on computes from it
(sampled points, mesh, stitch walks, engine payload) live in the same object, and
an instance chain keeps one such object per copy, held in step by writing every
edit to every member by index. That is why one sketch exists N times, why copies
can drift apart, and why every operator has to keep a set of cache flags correct
by hand.

## What Changes

- Add **Sketch**: the authored vector geometry of a panel - its vertices, edges,
  handles, spline points and internal lines - held once per instance chain,
  together with the editor's own draw points and the first section stage: the
  sections of every edge plus the pieces a crossing cuts them into, with the
  inside/outside classification of an internal line.
- Leave **Pattern** with identity, placement and derived data: name, anchor,
  rotation, mirror flag, grain direction, fabric, collision layer, granularity,
  simulation state and chain membership on one side; sampled points, mesh, stitch
  walks and the engine payload on the other.
- Replace the per-copy write convention with one contract: an edit writes the
  Sketch once, and the Sketch marks every Pattern that reads it; a consumer
  rebuilds a marked Pattern when it needs its derived data.
- Make the section stage of a Sketch independent of a panel's granularity, so
  which pieces a sketch consists of is a property of the Sketch alone.
- **BREAKING**: a copy no longer holds vector geometry of its own. Copying shares
  the Sketch; detaching gives one Pattern a private copy of it. Every place that
  reaches a panel's vertices or edges - an operator, a panel, a script - goes
  through the Sketch.
- **BREAKING**: nothing converts a scene saved by an earlier build. The two
  layers are what is saved and read; the add-on has not been released, so a scene
  that has to be carried over is converted by hand.

## Capabilities

### New Capabilities

- `pattern-layers`: the Sketch a chain shares, the signal a write sends to the
  Patterns that read it, the rebuild a consumer runs, detaching a Pattern from
  its chain, the placement and simulation state that stay per Pattern, and what
  is stored with the project.

### Modified Capabilities

- `agent-pattern-authoring`: the instance-chain rule changes from "an edit is
  written to every member" to "one Sketch, edited once, seen by every member",
  and a copy is stated to share its source's Sketch rather than duplicate it.

## Impact

- Model: a panel's own vertices, edges and internal lines move into a Sketch
  object; the Sketch sends the signal and the panels carry the flags that follow
  from it.
- Editing operators: every tool that changes topology writes the Sketch and
  stops there; the drift refusal and the per-member write loops disappear.
- Display and picking: the editor draws a Sketch's own draw points per Pattern,
  and a picked element resolves to the Sketch element together with the Pattern
  it was picked on.
- Sewing: a seam side names the Pattern it belongs to and the Sketch element it
  runs along; its stitch walk becomes derived data of that Pattern.
- Simulation bridge and generators: a prepare rebuilds every marked Pattern
  before exporting; a generator writes a Sketch and places the Patterns it owns.
- Surfaces: the script surface and `docs/agent-api.md` name Sketches and
  Patterns separately; existing calls keep their names where the behavior is
  unchanged.
- Engine: unchanged - it still receives one mesh payload per Pattern.
