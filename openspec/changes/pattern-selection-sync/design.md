## Context

See `proposal.md` - Why. Current state that shapes the approach:

- The pattern editor keeps its selection twice: the `is_selected` flag on each
  pattern (which the drawing reads) and `project.selected_patterns`, a list of
  uuids that the operators read. Both are written together by
  `operators/select.py`.
- A pattern's mesh object points back at its pattern through
  `obj.qmyi_simulation_props.pattern` / `.pattern_uuid`; a collider has no
  pattern.
- An instance chain is a circular `instance_next_uuid` list, and
  `model/generator.py:instance_chain()` already returns a pattern plus its copies.
- The 3D viewport's own selection is `context.selected_objects`; the pattern
  editor's selection is not visible to Blender's selection system at all.
- A pure selection change in the 3D viewport does not reliably run a depsgraph
  handler, and the add-on has no selection-time hook of its own.
- The pattern window draws every outline in one colour
  (`gizmos/temp_draw_manager.py`), with the pattern renderer's
  `draw_edges(color)` not taking a width.

## Goals / Non-Goals

**Goals:**

- One pattern = one selection, whichever editor it was made in, including the
  instance chain.
- A selection that is visible at a glance in every display mode.
- No coupling to geometry or to the simulation: the sync is display state.

**Non-Goals:**

- Syncing the sub-selection (vertices and edges) or the sewing selection. Only
  whole patterns take part; the edge-mode selection has no 3D counterpart.
- Selecting the collider objects from a pattern (a pattern and the body are not
  the same thing).
- A general selection framework, or hooks into Blender's own selection system.
- Highlighting a selected pattern in the 3D viewport (Blender already outlines the
  selected object).

## Decisions

### D1. One timer polls both sides

`selection_sync.py` runs one timer at 100 ms and compares two signatures: the
chains of the selected pattern meshes, and the chains of the patterns selected
in the editor. Whichever side changed since the last apply is written to the
other.

*Alternative:* a `depsgraph_update_post` handler. Rejected: a pure selection
change does not reliably run a depsgraph handler, so the mirror would appear to
work only sometimes, which is worse than a 100 ms delay.

*Alternative:* `bpy.msgbus` on `Object.select`. Rejected for now: it needs an
owner, careful subscription cleanup and a way to reach the pattern editor's own
selection (which is not an RNA property Blender tracks), so it would still end
up polling one side. The timer can be replaced by msgbus later without changing
the module's interface.

### D2. The last applied state lives on the scene, not in the module

The two signatures are stored as temp data on the scene's Qianyi settings, so
they are per scene, survive nothing (temp data is not saved) and disappear when
the add-on reloads - a fresh session adopts the selection it finds. A busy flag
around each apply stops the write from being read back as a new change.

### D3. Exactly the selected patterns are mirrored, not their instance chains

The mirror is one pattern for one pattern. An instance copy is a convenience for
editing the same pattern twice - editing already writes to every member of the
chain - but it is a separate place in the scene, and a pattern maker selecting
one of them is usually pointing at that one. Expanding to the chain would also
make the selection impossible to narrow from either side, because any single
member would immediately select all of them again.

### D4. Only pattern meshes take part, and a broken link is ignored

The 3D side is filtered by `qmyi_simulation_props.is_pattern_mesh`, so the body,
the colliders and any imported prop keep their selection; a mesh whose pattern has
been removed raises on lookup and is skipped rather than aborting the poll.
Objects outside the active view layer are not touched.

### D5. Both halves of the pattern-editor selection are written together

`apply_to_patterns` writes the `is_selected` flags (what the drawing reads) and
rebuilds `project.selected_patterns` (what the operators read) in one pass, and
refreshes the uuid map first, because the operators resolve through it and a
session that just loaded a file has an empty map.

### D6. The highlight is a second outline, not a mode of the first

`PatternRenderer.draw_edges` gains a line width, and the draw loop draws the
ordinary outline and then, for a selected pattern, a second pass in the highlight
colour at a wider width. The width is set explicitly on every call, so the
highlight cannot leak into the next pattern's lines.

*Alternative:* recolour the single outline for a selected pattern. Rejected: on a
`mesh` or `solid` pattern a slightly different colour is easy to miss, and the
invalid-outline colour (red) already occupies the "different colour" slot.

## Risks / Trade-offs

- [A 100 ms delay before the other side updates] -> accepted: the poll is cheap
  and the delay is below the time it takes to move the pointer between the
  editors.
- [A user who selects in both editors within one poll] -> the 3D side wins that
  round, because it is compared first; the next change in either editor wins the
  next round. Documented rather than made configurable.
- [The timer keeps running with the toggle off] -> the poll returns after one
  flag read, and turning the toggle off clears the remembered signatures.
- [Writing `selected_patterns` from the timer could fight an operator that is
  mid-selection] -> the apply only runs when a side's signature changed, and a
  selection operator sets the flag the signature is built from, so the next poll
  applies the finished selection rather than an intermediate one.
- [The highlight hides the invalid-outline marker] -> the marker is drawn after
  the highlight, so a crossing outline stays visible on a selected pattern.

## Migration Plan

Purely additive: the toggle defaults to off, so every existing session behaves
exactly as before until it is switched on. No saved data changes (the toggle is
one scene property, the sync bookkeeping is temp data). Rollback is reverting
the change.

## Open Questions

- Whether the sewing and edge selections should follow the pattern selection into
  3D (today the 3D side has nothing to show for them).
- Whether a pattern's mesh should be highlighted in the 3D viewport with the same
  colour used in the pattern window; Blender's own selection outline is enough
  for now.
