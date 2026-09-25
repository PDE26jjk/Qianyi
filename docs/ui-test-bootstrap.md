# UI test bootstrap: workspace, project tree, tool and N panel

How to put a running Blender into the state a UI test of this add-on expects,
in the order the add-on itself requires. Companion to
`docs/ui-input-automation.md` (how to compute coordinates, inject the mouse and
verify through data).

Detection of the add-on is by capability, not by the add-on registry: the
maintainer registers `qmyi` from a script, so `bpy.context.preferences.addons`
stays empty. Use `hasattr(bpy.ops, 'qmyi')` (or the presence of
`QianyiNodeTree` node groups) as the availability test.

## 0. Availability check

```python
if not hasattr(bpy.ops, 'qmyi'):
    raise RuntimeError("qmyi is not registered in this Blender session")
```

Related facts used below: the project type is `QianyiNodeTree`
(`bpy.data.node_groups` instances, `scene.qmyi.active_project_index` selects
the active one), the node editor panels carry the categories `Project`,
`Pattern`, `Fabric`, `GC Library`, and the 3D viewport panel category is
`Qianyi`.

## 1. Workspace

- If the caller named a workspace, switch to it:

```python
w = bpy.context.window
ws = bpy.data.workspaces.get(name)
if ws:
    w.workspace = ws
```

- Otherwise inspect the current workspace. It is usable when it provides both a
  `VIEW_3D` area and a Qianyi editor, i.e. a `NODE_EDITOR` area whose
  `spaces.active.tree_type == 'QianyiNodeTree'`:

```python
areas = w.screen.areas
has_3d = any(a.type == 'VIEW_3D' for a in areas)
has_qianyi = any(a.type == 'NODE_EDITOR' and a.spaces.active.tree_type == 'QianyiNodeTree'
                 for a in areas)
```

- If either is missing, create a workspace named `Qianyi` and put it into the
  standard state - `VIEW_3D` on the left, Qianyi node editor on the right:

```python
bpy.ops.workspace.duplicate()               # copy the current layout
w = bpy.context.window
w.workspace.name = 'Qianyi'                 # read the name back if it must be exact
main = max(w.screen.areas, key=lambda a: a.width * a.height)
region = next(r for r in main.regions if r.type == 'WINDOW')
before = {a.as_pointer() for a in w.screen.areas}
with bpy.context.temp_override(window=w, area=main, region=region):
    bpy.ops.screen.area_split(direction='VERTICAL', factor=0.5)
new_area = next(a for a in w.screen.areas if a.as_pointer() not in before)
new_area.type = 'VIEW_3D'
main.type = 'NODE_EDITOR'
```

## 2. Activate the Qianyi node tree (project)

```python
trees = [g for g in bpy.data.node_groups if g.bl_idname == 'QianyiNodeTree']
if not trees:
    bpy.ops.qmyi.add_project()              # the add-on's own creator: makes the tree
    trees = [g for g in bpy.data.node_groups if g.bl_idname == 'QianyiNodeTree']

idx = bpy.context.scene.qmyi.active_project_index
tree = bpy.data.node_groups[idx] if idx < len(bpy.data.node_groups) else trees[0]
for area in w.screen.areas:
    if area.type == 'NODE_EDITOR':
        area.spaces.active.tree_type = 'QianyiNodeTree'
        area.spaces.active.node_tree = tree
```

Order matters: the add-on hides its tools and panels while
`space.tree_type != 'QianyiNodeTree'`, so the tree is set before any tool or
panel work.

## 2b. Refresh the identities before driving the UI

The add-on's temp-data cache assigns `global_idx` and `global_uuid` lazily, and
Blender refuses that write inside a panel draw or an operator poll. Commit the
identities from a script context first, and repeat after anything that clears
them (opening a file, undo, redo):

```python
from qmyi.model.model_data import refresh_all_uuids

refresh_all_uuids()
for tree in (g for g in bpy.data.node_groups if g.bl_idname == 'QianyiNodeTree'):
    tree.get_temp_data()                 # commits the slot; a script context may write
    for pattern in tree.patterns:
        pattern.get_temp_data()
```

Never assign `global_idx` yourself - it is the index every reference resolves
through, and rewriting it breaks them. If a call fails with "Writing to ID
classes in this context is not allowed", refresh the identities as above and
retry instead of touching the index.

Verified: after this preparation a full window redraw performed zero refused
writes and did not grow `global_data.temp_data`.

## 3. Activate the Qianyi select tool

The select tool the pattern-editing test needs is the one that lives in the 2D
pattern editor (the Qianyi node editor): class `NODE_T_qmyi_select`, id name
`qmyi.select`, `bl_space_type = 'NODE_EDITOR'`, preselection gizmo group, and a
cursor callback that switches `scene.qmyi.edit_sub_mode` to `EDGE_VERTEX`.

Activate it with a context override on that area, and read it back from the node
space:

```python
area = next(a for a in w.screen.areas
            if a.type == 'NODE_EDITOR' and a.spaces.active.tree_type == 'QianyiNodeTree')
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(window=w, area=area, region=region,
                               space_data=area.spaces.active):
    bpy.ops.wm.tool_set_by_id(name='qmyi.select')

tool = w.workspace.tools.from_space_node(create=False)   # 'create' must be a keyword
assert tool and tool.idname == 'qmyi.select'
```

Verified: the call returns `FINISHED` and the read-back reports `qmyi.select`;
with the Qianyi tree active the node editor's built-in tools are filtered out
(`builtin.select_box` returns `CANCELLED`), which is a useful confirmation that
the add-on's tool context is the one in effect.

The add-on also registers a viewport tool, `VIEW3D_T_qmyi_pick_mesh`, under its
own id name `qmyi.pick_mesh` (`bl_space_type = 'VIEW_3D'`, mode `OBJECT`). A
viewport-side test activates it the same way, with a `VIEW_3D` override, and
reads back through
`w.workspace.tools.from_space_view3d_mode('OBJECT', create=False)` (verified:
`builtin.select_box` -> `qmyi.pick_mesh`).

## 4. Switch the Qianyi N panel to Project or Pattern

The sidebar category tabs hold no RNA state, so the switch is a click (see the
injection recipe in `docs/ui-input-automation.md`). Open the sidebar first:

```python
space = <the Qianyi node editor space>
space.show_region_ui = True
```

The tabs are stacked top-down in this order and are evenly spaced:

```
0 Group   1 Tool   2 View   3 Project   4 Pattern   5 Fabric   6 GC Library
```

Measured on the maintainer's machine (physical pixels, 150 % scale):

```
x        = UI_region.right - 16
y_top    = 77 + 68 * index          # below the top edge of the area
```

so `Project` is index 3 and `Pattern` is index 4. Verified: clicking index 4
expanded the `Patterns` panel (pattern list, Property values, Entities).

Confirmation is visual - take an editor screenshot after the click
(`screen.screenshot_area`), since the expanded category is not readable from
RNA.

## 5. Result

After the five steps the session is in the standard test state:

- a workspace with `VIEW_3D` left and the Qianyi node editor right, showing the
  active project tree,
- the `qmyi.select` (3D) tool active in the viewport,
- the Qianyi sidebar showing `Project` or `Pattern`.
