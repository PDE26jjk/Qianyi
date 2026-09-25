## 1. The toggle

- [x] 1.1 Add `sync_selection` to the scene's Qianyi settings, default off, with
  the same meaning the outliner's and the UV editor's sync toggle has
- [x] 1.2 Draw the toggle in the pattern editor's header with the
  `UV_SYNC_SELECT` icon, and verify it appears next to the display-mode
  dropdown and reads back from `scene.qmyi`
- [x] 1.3 Verify that turning the toggle on adopts the current selection on both
  sides without changing either, and that turning it off stops the sync and
  clears the remembered state

## 2. The mirror

- [x] 2.1 Read the 3D side as the selected pattern meshes, ignoring colliders
  and any other object
- [x] 2.2 Read the pattern-editor side as the selected patterns
- [x] 2.3 Apply a selection to the pattern editor by writing both the
  `is_selected` flags and the `selected_patterns` uuid list, refreshing the uuid
  map first
- [x] 2.4 Apply a selection to the 3D viewport by selecting exactly the meshes
  of the chosen patterns and leaving every non-pattern object alone
- [x] 2.5 Keep the last applied signatures and a busy flag as scene temp data so
  an apply is never mirrored back, and make a mesh whose pattern is gone be
  skipped instead of failing the poll
- [x] 2.6 Run the poll from one timed callback registered with the add-on, at
  100 ms, and verify the module registers and unregisters with it

## 3. Verify the mirror

- [x] 3.1 Verify 3D to pattern editor: selecting one pattern's mesh selects that
  pattern and not another, and clearing the mesh selection clears the patterns
- [x] 3.2 Verify pattern editor to 3D: selecting a pattern selects its mesh and
  deselects the mesh of an unselected pattern
- [x] 3.3 Verify an instance copy is not selected when one member of the chain
  is selected on either side
- [ ] 3.4 Verify in a live session that a collider selected in 3D leaves the
  pattern selection alone and stays selected itself
- [ ] 3.5 Verify in a live session that moving a vertex with the sync on adds no
  undo step and changes no geometry

## 4. The selection highlight

- [x] 4.1 Give the pattern renderer's outline call a line width, set explicitly
  on every call so the width cannot leak between patterns
- [x] 4.2 Draw a second, thicker outline in a dedicated highlight colour for a
  selected pattern, after its ordinary outline and its internal lines
- [ ] 4.3 Verify in a live session that the highlight is drawn in every display
  mode and disappears
  when the pattern is deselected, and that the invalid-outline marker still shows
  on a selected pattern
