## Why

A panel exists twice in the add-on: as a mesh object in the 3D viewport and as a
pattern in the pattern editor. Selecting one currently says nothing to the
other, so a pattern maker who picks a panel on the body has to find it again by
name in the editor, and a selection made in the editor is invisible on the body.
On top of that, the pattern window outlines every panel in the same colour, so
in display modes other than `mesh` the selection cannot be read off the screen
at all.

## What Changes

- Add a **Sync Selection** toggle to the pattern editor's header, the way the
  UV editor and the outliner have one, stored on the scene's Qianyi settings
  and off by default.
- With it on, the two selections mirror each other:
  - selecting a panel's mesh in the 3D viewport selects that panel in the
    pattern editor, together with the other members of its instance chain, and
    deselects the panels that are no longer selected;
  - selecting panels in the pattern editor selects their meshes in the 3D
    viewport, again with the chain;
  - clearing either side clears the other.
- Only pattern meshes take part. Colliders, the body and any other object keep
  their selection, and a panel with no mesh has nothing to select in 3D.
- Give a selected panel a **highlighted outline** in the pattern window: a
  second, thicker outline in a highlight colour, drawn over the ordinary one, in
  every display mode. Today the outline is the same white for every panel, so a
  selection is unreadable unless the `mesh` mode happens to show it.

## Capabilities

### New Capabilities

- `panel-selection-sync`: the header toggle, the two-way mirroring of the 3D
  and pattern-editor selections (with instance chains), the rules for what does
  and does not take part, the guarantee that the mirror cannot loop or touch
  geometry, and the highlighted outline that makes the selection visible in the
  pattern window.

### Modified Capabilities

(none - no existing specification covers the selection of panels)

## Impact

- Settings: `Qianyi/model/qianyi_data.py` (the toggle, plus the last-applied
  signatures it keeps as scene temp data).
- New module: `Qianyi/selection_sync.py` (the mirror and its poll), registered
  with the add-on so the timer follows its lifetime
  (`Qianyi/registration.py`).
- Selection model: `Qianyi/model/qianyi_project.py` (`selected_patterns` and the
  `is_selected` flag on each pattern are written together) and
  `Qianyi/model/generator.py` (`instance_chain` decides what "the panel" means).
- Drawing: `Qianyi/gizmos/temp_draw_manager.py` (the highlight pass) and
  `Qianyi/gizmos/pattern_renderer.py` (a line width per outline call).
- UI: `Qianyi/ui/header.py` (the toggle button).
- Engine and the simulation payload: untouched - selection is display state.
