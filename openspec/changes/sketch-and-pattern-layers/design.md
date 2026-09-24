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

The engine is not affected: it receives one mesh payload per Pattern and does not
know how the Pattern was authored.

## Goals / Non-Goals

**Goals:**

- One authored Sketch per instance chain, with a single write path and no
  per-member bookkeeping.
- One signal per write, sent by the Sketch to every Pattern that reads it, so no
  caller has to remember which members to update.
- A rebuild contract that says who computes derived data, when, and what happens
  when it cannot be computed.
- A first section stage (sections, crossing cuts, inside/outside marking) that is
  a property of the Sketch and does not move with a pattern's granularity.

**Non-Goals:**

- Changing the engine, the simulation payload shape, or how a mesh is sampled.
- Making the derived data shared between patterns: two patterns of one Sketch
  still have their own granularity, mesh object and simulation state.
- Carrying a file saved by an earlier build over. The add-on is not released and
  the maintainer converts a scene by hand when one has to be carried over; see
  D9.
- Editing rules for generated panels, seam spans and display modes; the changes
  in flight for those keep their own contracts and only have to respect the layer
  boundary.

## Decisions

### D1 - Two layers, named Sketch and Pattern

The authored vector geometry becomes one object, the **Sketch**; the placed panel
stays the **Pattern** and keeps identity, placement and derived data. The Sketch
is one per instance chain and the Pattern is one per placed panel, so the layer
count is two.

Alternatives: **topology/geometry** - rejected, both words are already used for
the opposite halves (`geometry` is the vector primitives, `pattern_geometry` is
the editing commands, the engine module named `geometry` is the triangulator),
and in graphics topology means connectivity while geometry means positions,
which is the reverse of this split; **primitive/instance** - rejected,
`primitive` is taken by the generator components; **skeleton/content** - rejected
as a code name, too vague for the Pattern half (it is a good metaphor in
conversation, not a directory name); **outline/mesh** - rejected, the Sketch is
not only the outline (internal lines) and the Pattern is not only a mesh
(samples, stitch walks, payload). **shape/piece** was considered as an internal
vocabulary and dropped in favour of the two names above.

### D2 - One Sketch per instance chain, detach as the escape hatch

A chain holds one Sketch and the patterns reference it. Copying shares the Sketch
instead of duplicating it, and **detach** gives one Pattern a private copy of the
Sketch so that two patterns can still diverge when the pattern maker wants that.

Alternatives: **keep per-member copies and add a drift guard** - rejected, that
keeps the N-fold write and the "which member decides" question; **copy-on-write
for every edit** - rejected, it silently unlinks a chain on the first edit;
**no detach** - rejected, the model would then be unable to express two patterns
of one origin with different Sketches.

### D3 - The Sketch sends the signal, the flags carry it

Every edit of a panel's geometry goes through the Sketch it reads, and the Sketch
is what tells the panels about it: `Sketch.geometry_written` walks the patterns
whose `sketch_uuid` is its own and calls `Pattern.mark_geometry_changed` on each,
which marks the outline state, the panel's own copy of the first stage, its
samples, its render line and the sewings that reach it. A tool that edits writes
the Sketch and lets that call do the marking; a tool that changes only what a
panel owns (placement, granularity, fabric, collision layer) marks the panel
itself and nothing else.

An earlier draft carried a `revision` counter on the Sketch and a
`baked_revision` record on the Pattern, with "stale" meaning the two differ. It
was dropped: the flags already say what is out of date, a counter only adds a
second thing every write path has to remember to raise (and a chain of N members
raises it N times unless a writer also learns to count edits), and nothing in the
add-on needs a number rather than a flag. Marking is what a write does; the
rebuild is what a reader does.

Alternatives: **keep the flag set** - that is what the add-on already has, and
what the layers make coherent: the Sketch owns the writes, so exactly one call
maintains the flags of a whole chain.

### D4 - The first section stage belongs to the Sketch

The Sketch owns the sections of its edges, the pieces crossings cut them into,
and the inside/outside marking of an internal line. This stage is measured on the
Sketch's own curve samples and MUST NOT use a pattern's granularity, so the
decomposition of a Sketch is the same for every Pattern that references it, so it
is built once and only the panels clone it.

The measurement is a fixed step in millimetres (`MEASURE_STEP_MM`, 0.5 mm, and no
piece shorter than `MIN_PIECE_MM` is cut): the crossing search needs uniform
samples to map a returned position back onto a piece, and a step that came from a
panel would put the decomposition back under that panel's control. Sampling for a
mesh stays where it is - a Pattern's own pass, at its own granularity - because
two patterns of one Sketch may sample it differently.

Alternatives: **keep the crossing pass in the Pattern path over
granularity-resampled points** - rejected: the number of pieces would then follow
the sampling density, so two patterns of one Sketch could disagree about what the
Sketch is, and the result could not be cached on the Sketch; **compute the cuts
lazily when a panel clones the stage** - rejected: the cuts are what the editor marks as inside
and outside, so they belong to the stage the editor reads.

### D5 - The consumers rebuild, the drawing path only draws

`ensure_sections` is where a marked panel rebuilds: it refreshes the Sketch's
first stage, clones the panel's own copy and samples it. The mesh path runs it
before it samples, and a simulation prepare runs it for every panel it is about
to send. It is never called by an edit's marking and never by the drawing path -
the editor draws what the Sketch has and leaves a marked panel alone. A rebuild
that cannot run (crossing or degenerate outline) keeps the last good derived data
and records the reason in `mesh_error`, which is the existing crossing policy.

Alternatives: **rebuild inside every edit** - rejected, that is why an edit used
to cost N meshes; **rebuild inside the drawing path** - rejected, drawing must
not change the scene.

### D6 - What stays on the Pattern

Name, anchor, rotation, mirror flag, grain direction, fabric, collision layer,
granularity, mesh object, simulation state, chain membership and the derived data
all stay on the Pattern. Changing any of them marks no geometry,
because none of them is a property of the Sketch.

### D7 - A seam is defined on patterns and walked as derived data

A seam side names its Pattern, a Sketch element of that Pattern and a position on
it; the stitch walk (sections, link identities, stitch pairs) is derived data of
the two patterns and is rebuilt when either panel is marked. This is the
same direction the `sewing-many-to-many` change in flight already takes by making
a span name its panel; that change and this one agree, and the only thing this
change adds is that the walk follows the same marked/rebuild rule as the rest.

Alternatives: **let the seam name an edge identity alone** - rejected, one Sketch
element is on screen in several patterns, so the identity would no longer say
which Pattern is meant.

### D8 - Identity of a Sketch element and of a pick

A Sketch element carries its own stable identity across rebuilds; a picked element
resolves to the Sketch element together with the Pattern it was picked on.
Selection stores that pair where the Pattern matters (a seam side, a per-pattern
property) and the Sketch element alone where it does not (moving a vertex,
deleting an edge).

Alternatives: **give every Pattern its own element identities** - rejected, that
is the duplicated model again and it is what forces per-member write loops.

### D9 - No compatibility path

The two layers are what is stored and read. A scene saved before this change is
not converted, and nothing invents a Sketch for a panel that has none: the
maintainer converts a scene by hand when one has to be carried over, because the
add-on has not been released and there is no installed base to keep.

Alternatives: **adopt a panel's existing collections into a private Sketch on
first touch** - rejected by the maintainer as unnecessary work for an unreleased
add-on; **guess which panels used to be copies** - rejected, the old data does
not say, and a wrong guess silently welds two Sketches together.

### D10 - The editing contract for tools

A tool that changes topology writes the Sketch and stops: no sampling and no seam
relink inside the write. The Sketch marks the panels that read it, and the tool
then meshes them - "a topology edit meshes before it returns". The tools keep
their own immediate checks - a self-intersection test on the candidate points is
a question about the Sketch and stays in the tool - but a tool MUST NOT ask for
derived data. Tools that only change placement write the Pattern and mark no
geometry.

### D11 - What this makes unreachable

With one Sketch per chain, a chain whose members disagree about their geometry
cannot exist. The refusal that reported a drifted copy, and the "detach or
rebuild" hint that goes with it, become unreachable and are removed; the
`pattern-edge-tools` requirement that describes that refusal is dropped when that
change is archived. The detach this change adds is the supported way to let a
pattern diverge.

### D12 - The pick table lives on the pattern

The ids the editor picks with are not the elements' own identities: a Pattern
keeps a temporary table of the selectable things it draws - an edge, a point, a
spline control point, a Bezier handle - each with an id it generates (incrementing
or random) for the current session, and the id pass draws those entries with their
ids. A pick reads an id back and answers with the element *and the Pattern* it was
generated for. The table is session data and is never saved, and the renderer an
element draws itself with can stay where it is: it draws the shape, the table
decides what a click means.

Alternatives: **keep picking by the element's own identity** - rejected, one
Sketch element is on screen in every member of its chain, so the pick cannot say
which panel was clicked - and a drag then has to guess which member's settings
(granularity, fabric, transform) to use; **one table for the whole project** -
rejected, the ids would have to be rebuilt on every change of any panel, and the
table is exactly the per-panel state this change is separating out.

### D13 - A seam change invalidates copies, it does not rebuild them at once

Linking a seam splits sections, and the sections of a seam reach every panel of
its connected component, so adding, removing or moving one seam can invalidate the
section copy of any of them, and a linking run can leave a copy cut where the new
seam graph does not agree. The rule is therefore: a change to the sewing graph, or
to a Sketch, marks the section copy, the samples and the mesh of every pattern in
the affected chains stale, and the rebuild happens when a consumer asks for it -
the display path when it draws a panel, the simulation when it prepares. An edit
that changes topology is not in this group: it rebuilds the mesh of the panel it
changed before it returns, as it does today. What is deferred is only a change
that can move the pieces a mesh is built from without being a topology edit: a
seam edit, whose linking run cuts sections in every pattern it reaches. A change
of granularity is not deferred: it is the panel's own sampling size, so the panel
it was changed on is sampled and meshed again there and then, like a topology
edit. A fabric, a
placement, a display setting, a collision layer, a grain direction or a
simulation state changes neither a section nor a sample: none of those is a
reason to rebuild anything, and the engine payload that carries them is assembled
when a simulation prepares. A copy is never patched: it is cloned again from the
Sketch, so a wrongly cut copy cannot survive.

### D15 - The samples are kept on the pattern, as a copy written before the mesh

The samples a mesh is built from are session data: they are taken from the Sketch
at this panel's granularity whenever they are needed, and a reload takes them
again. They are also written to the pattern's own `geo_points` right before the
mesh is generated, from the very points that mesh is generated from. That copy is
not read by the add-on - it exists so a check that runs without opening Blender
can read a panel's shape out of the saved file, at that panel's own granularity.

Alternatives: **keep the copy on the edge, as before** - rejected, one edge is
shared by every member of a chain, so two panels with different granularities
would overwrite each other's copy; **write it at save time** - rejected, a save
can happen with stale or missing samples, and the rule "the copy is what the mesh
was built from" only holds at the moment the mesh is built.

Alternatives: **rebuild every affected panel on every seam edit** - rejected, that
is what makes editing a seam slow today, and the result is thrown away by the next
edit in the same gesture; **patch the existing copy** - rejected, a cut that a
later linking run disowns is not something the copy can undo, which is why the
stage it came from has to be the source.

### D14 - Stage one is a raw section: a span, not a sampled piece

`SectionRaw` is what the Sketch stores and copies: the edge, the span of that edge
(`start_pos`, `end_pos`), and the crossing marks (`io_state`, `outsize`). It
carries no sampling state at all - no segment count, no sample offsets, no mesh
offsets. A Pattern clones a raw chain into its own `Section` objects, and those
carry what is per panel: the segment count at that panel's granularity, the sample
offsets and the mesh offsets. Cloning is then a cheap copy of spans, and there is
no place on the shared object where two panels could fight over a number.

Alternatives: **one Section class with the sampling fields left unset on the
Sketch's copy** - rejected: nothing stops a caller from reading a field that only
makes sense after a panel filled it in, which is the class of bug this whole
change exists to remove; **store the raw stage as plain tuples** - rejected, the
crossing marks and spans are read by name throughout the section code and the
chain links are what make a walk cheap.

## Risks / Trade-offs

- **Sharing does not shrink the rebuild work** -> a chain of N patterns still builds
  N meshes, because each Pattern has its own granularity and transform.
  Mitigation: rebuild only what a consumer asks for, keep the drawing path
  read-only, and expect the win in the model layer (one write, one section stage)
  rather than in mesh time.
- **A Sketch with no patterns left** -> Blender does not collect unreferenced
  property groups, so a Sketch can outlive its last Pattern. Mitigation: removing
  the last Pattern of a chain removes the Sketch, and a probe asserts it.
- **Undo and reload clear the session data** -> derived data and the marks that
  describe it are session state, which undo and a reload do not restore.
  Mitigation: the marks start out saying "not built", so the next consumer
  rebuilds instead of trusting a blank cache.
- **Every consumer has to be re-pointed at the Sketch** -> the biggest risk is a
  caller that still reaches a Pattern's own geometry. Mitigation: the Pattern has
  no vector collections at all after the rewrite, so a straggler fails loudly at
  import or first call rather than producing a wrong mesh, and the probes cover
  the interactive tools end to end.
- **Two changes in flight touch the same seam model** -> `sewing-many-to-many`
  already makes a span name its panel. Mitigation: D7 adopts that rule instead of
  inventing a second one, and this change does not restate span behaviour.
- **Script-compatibility** -> a caller that reads a panel's vertices keeps its
  call; the answer is the panel's Sketch. Mitigation: the surface keeps its names
  where behavior is unchanged, and `docs/agent-api.md` is updated in the same
  change.

## Migration Plan

1. Introduce the Sketch object with its identity, its elements and its first
   section stage, and give the Pattern a reference to one.
2. Send one signal per write from the Sketch to the Patterns that read it, and
   keep the flags the consumers already use to decide what to rebuild.
3. Give the Pattern placement, chain membership and detach; drop the per-member
   write loops and the drift refusal.
4. Re-point the operators, the drawing and picking path, the seams, the prepare
   path and the generators at the two layers.
5. Update the script surface and its documentation, then run the existing probes
   plus a new layered-model probe and one live session.

Rollback: the change is one rewrite of the model with no runtime flag. Nothing
converts an older scene (D9), so the mitigation is a backup copy of a scene
before a session is used to try it, not a switch.

## Open Questions

- Where the detach affordance lives in the UI (pattern editor context menu versus
  the panel list) is deferred; the behavior and the script call are specified,
  the affordance is not.
