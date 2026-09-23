## Context

See `proposal.md` - Why. Three properties of the current model shape this
design:

1. The authored vector geometry and everything derived from it are the same RNA
   object, so a cache (samples, sections, mesh, stitch walk) and a source of
   truth (a vertex position) have the same lifetime and the same addressing.
2. An instance chain is a list of panels that each hold their own copy of that
   geometry, kept in step by index; the copies are not derivable from each other,
   which is what makes drift possible and every write N-fold.
3. Caches are invalidated by flags that each caller has to set and clear
   correctly. Forgetting one is a silent wrong result, not a loud failure.

The engine is not affected: it receives one mesh payload per piece and does not
know how the piece was authored.

## Goals / Non-Goals

**Goals:**

- One authored shape per instance chain, with a single write path and no
  per-member bookkeeping.
- A revision that makes "is this derived data still valid" a single comparison.
- A bake contract that says who computes derived data, when, and what happens
  when it cannot be computed.
- A first section stage (sections, crossing cuts, inside/outside marking) that is
  a property of the shape and does not move with a panel's granularity.

**Non-Goals:**

- Changing the engine, the simulation payload shape, or how a mesh is sampled.
- Making the derived data shared between pieces: two pieces of one shape still
  have their own granularity, mesh object and simulation state.
- A new file format version. Saved scenes are read by adopting what they already
  hold (see the migration plan).
- Editing rules for generated panels, seam spans and display modes; the changes
  in flight for those keep their own contracts and only have to respect the
  layer boundary.

## Decisions

### D1 - Two layers, named shape and piece

The authored vector geometry becomes one object, the **shape**; the placed panel
becomes the **piece** and keeps identity, placement and derived data. Both are
per-instance-chain and per-piece respectively, so the layer count is two.

Alternatives: **three layers** (shape, placement, derived) - rejected, placement
and derived are one-to-one with a piece, so the extra layer buys nothing;
**naming it topology/geometry** - rejected, both words are already used for the
opposite halves (`geometry` is the vector primitives, `pattern_geometry` is the
editing commands, the engine module named `geometry` is the triangulator), and
in graphics topology means connectivity while geometry means positions, which is
the reverse of this split; **primitive/instance** - rejected, `primitive` is
taken by the generator components; **skeleton/content** - rejected as a code
name, too vague for the second half (it is a good metaphor in conversation, not
a directory name); **outline/mesh** - rejected, the first half is not only the
outline (internal lines) and the second half is not only a mesh (samples, stitch
walks, payload).

### D2 - One shape per instance chain, detach as the escape hatch

A chain holds one shape and the pieces reference it. Copying shares the shape
instead of duplicating it, and **detach** gives one piece a private copy of the
shape so that two pieces can still diverge when the pattern maker wants that.

Alternatives: **keep per-member copies and add a drift guard** - rejected, that
keeps the N-fold write and the "which member decides" question; **copy-on-write
for every edit** - rejected, it silently unlinks a chain on the first edit;
**no detach** - rejected, the model would then be unable to express two pieces
of one origin with different shapes.

### D3 - A revision, not flags

A shape carries a revision that a write raises. A piece records the revision its
derived data was baked from, and derived data is stale exactly when the recorded
revision differs from the shape's current one. A bake that could not run records
its reason and leaves the record behind, so the piece keeps reporting itself as
stale until a bake succeeds.

Alternatives: **keep the flag set** (`need_update_points`, `need_geo_update`,
`need_render_update`, `need_sewing_update`) - rejected, four flags per piece that
every caller must maintain, with a silent wrong result when one is missed;
**compare revisions with `>`** - rejected, an undo or a redo can restore an
older revision, and inequality answers "current" and "stale" correctly for both
directions.

### D4 - The first section stage belongs to the shape

The shape owns the sections of its edges, the pieces that crossings cut them
into, and the inside/outside marking of an internal line. This stage is measured
on the shape's own curve samples and MUST NOT use a panel's granularity, so the
decomposition of a shape is the same for every piece that references it and can
be baked against the shape revision.

Alternatives: **keep the crossing pass in the piece path over
granularity-resampled points** - rejected: the number of pieces would then follow
the sampling density, so two pieces of one shape could disagree about what the
shape is, and the result could not be cached on the shape; **compute the cuts
lazily at bake time** - rejected: the cuts are what the editor marks as inside
and outside, so they belong to the stage the editor reads.

### D5 - The bake contract

`bake(piece)` is the only entry point that computes derived data, it is
idempotent, and it is called by the consumers that need the data: the mesh path,
a simulation prepare, and any read that promises current samples. It is never
called by a shape write and never by the drawing path - the editor draws what the
shape has and marks a stale piece instead of pausing to sample. A bake that
cannot run (crossing or degenerate outline) keeps the last good derived data,
records the reason, and reports the piece as stale; this is the existing crossing
policy, now expressed as a bake outcome rather than a mesh-side special case.

Alternatives: **bake eagerly inside every edit** - rejected, that is the current
behaviour, and it is why an edit costs N meshes; **bake inside the drawing path**
- rejected, drawing must not change the scene.

### D6 - What stays on the piece

Name, anchor, rotation, mirror flag, grain direction, fabric, collision layer,
granularity, mesh object, simulation state, chain membership and the derived data
all stay on the piece. Changing any of them leaves the shape revision alone,
because none of them is a property of the shape.

### D7 - A seam is defined on pieces and walked as derived data

A seam side names its piece, a shape element of that piece and a position on it;
the stitch walk (sections, link identities, stitch pairs) is derived data of the
two pieces and is rebuilt when either shape revision moves. This is the same
direction the `sewing-many-to-many` change in flight already takes by making a
span name its panel; that change and this one agree, and the only thing this
change adds is that the walk is stale-checked like every other bake.

Alternatives: **let the seam name an edge identity alone** - rejected, one shape
element is on screen in several pieces, so the identity would no longer say which
piece is meant.

### D8 - Identity of a shape element and of a pick

A shape element carries its own stable identity across bakes; a picked element
resolves to the shape element together with the piece it was picked on. Selection
stores that pair where the piece matters (a seam side, a per-piece property) and
the shape element alone where it does not (moving a vertex, deleting an edge).

Alternatives: **give every piece its own element identities** - rejected, that is
the duplicated model again and it is what forces per-member write loops.

### D9 - Old scenes are adopted, not migrated

A shape stored in a file is read as it is. A panel loaded from an earlier build,
which has vertices, edges and internal lines but no shape, gets a private shape
adopted from those collections the first time it is touched, and is alone in its
chain. Nothing is linked up on load: two panels that were copies of each other
before are two pieces with a private shape each, and can be linked deliberately.

Alternatives: **refuse to load older panels** - rejected, a user's file would
lose its panels; **guess which panels used to be copies** - rejected, the file
does not say, and a wrong guess silently welds two shapes together.

### D10 - The editing contract for tools

A tool that changes topology writes the shape and stops: no sampling, no mesh, no
seam relink, one revision raise, one undo step. The tools keep their own immediate
checks - a self-intersection test on the candidate points is a question about the
shape and stays in the tool - but a tool MUST NOT ask for derived data. Tools
that only change placement write the piece and touch no revision.

### D11 - What this makes unreachable

With one shape per chain, a chain whose members disagree about their geometry
cannot exist. The refusal that reported a drifted copy, and the "detach or
rebuild" hint that goes with it, become unreachable and are removed; the
`pattern-edge-tools` requirement that describes that refusal is dropped when that
change is archived. The detach this change adds is the supported way to let a
piece diverge.

## Risks / Trade-offs

- **Sharing does not shrink the bake work** -> a chain of N pieces still builds N
  meshes, because each piece has its own granularity and transform. Mitigation:
  bake only what a consumer asks for, keep the drawing path read-only, and expect
  the win in the model layer (one write, one section stage) rather than in mesh
  time.
- **A shape with no pieces left** -> Blender does not collect unreferenced
  property groups, so a shape can outlive its last piece. Mitigation: removing the
  last piece of a chain removes the shape, and a probe asserts it.
- **Undo and reload clear the caches** -> derived data lives in session data,
  which undo and a reload do not restore. Mitigation: a missing bake record reads
  as stale, so the next consumer rebuilds instead of trusting a blank cache.
- **Every consumer has to be re-pointed at the shape** -> the biggest risk is a
  caller that still reaches a piece's own geometry. Mitigation: the piece has no
  vector collections at all after the rewrite, so a straggler fails loudly at
  import or first call rather than producing a wrong mesh, and the probes cover
  the interactive tools end to end.
- **Two changes in flight touch the same seam model** -> `sewing-many-to-many`
  already makes a span name its panel. Mitigation: D7 adopts that rule instead of
  inventing a second one, and this change does not restate span behaviour.
- **Script-compatibility** -> a caller that reads a panel's vertices keeps its
  call; the answer is the piece's shape. Mitigation: the surface keeps its names
  where behaviour is unchanged, and `docs/agent-api.md` is updated in the same
  change.

## Migration Plan

1. Introduce the shape object with adoption of an existing panel's collections,
   so a scene saved by an older build loads with one shape per panel.
2. Move the first section stage (sections, crossing cuts, inside/outside marking)
   into the shape and measure it on the shape's own samples.
3. Add the revision and the bake record; express the old cache flags as
   staleness where they are still needed and delete them where they are not.
4. Give the piece placement, chain membership and detach; drop the per-member
   write loops and the drift refusal.
5. Re-point the operators, the drawing and picking path, the seams, the prepare
   path and the generators at the two layers.
6. Update the script surface and its documentation, then run the existing probes
   plus a new layered-model probe and one live session.

Rollback: the change is one rewrite of the model with no runtime flag. A scene
saved by the new build cannot be read by an older build, so the mitigation is a
backup copy of a scene before a session is used to try it, not a switch.

## Open Questions

- Where the detach affordance lives in the UI (pattern editor context menu versus
  the panel list) is deferred; the behaviour and the script call are specified,
  the affordance is not.
