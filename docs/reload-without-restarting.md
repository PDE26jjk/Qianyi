# Reloading the add-on without restarting Blender

Restarting Blender drops the MCP socket - the `MCP for Blender` add-on hosts it
- so an agent that is driving the session loses its connection. The two add-ons
are independent, so reloading `qmyi` in-process keeps the MCP server, the open
file and the workspace layout alive while picking up edits to the project files.

## The reload script

Run this in a notebook cell, from `--python`, or through the MCP; after the
first import, call `reload()` whenever project files changed.

```python
import importlib
import importlib.util
import os
import sys


def import_package(path, module_name):
    """Import an add-on package from a directory (nothing has to be installed)."""
    init_path = os.path.join(path, "__init__.py")
    if not os.path.exists(init_path):
        raise FileNotFoundError(init_path)
    spec = importlib.util.spec_from_file_location(module_name, init_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


REPO = os.getcwd()
qmyi = import_package(os.path.join(REPO, "Qianyi"), "qmyi")


def reload():
    """unregister -> re-exec the package -> reload submodules -> register."""
    global qmyi
    try:
        qmyi.unregister()
    except Exception as error:
        print("unregister failed:", error)
    addon_modules = [name for name in sys.modules if name.startswith("qmyi.")]
    qmyi = importlib._bootstrap._exec(qmyi.__spec__, qmyi)
    for name in addon_modules:
        importlib.reload(sys.modules[name])
        # print(name)
    qmyi.register()
```

## Why the order matters

1. `unregister()` first: it removes the classes, workspace tools, gizmos and
   `bpy.app.handlers` entries the old module registered. A `@persistent` handler
   that is not removed keeps pointing at the old function object, so it would go
   on running the old code.
2. Re-executing the package module rebinds `qmyi` to the new file contents.
3. Reloading the submodules picks up edits in `Qianyi/model/`, `Qianyi/ui/`,
   `Qianyi/operators/`, ... .
4. `register()` last: everything is registered again against the new classes.

## Refresh the identities right after a reload

`global_data.temp_data` and `global_data.uuid2obj` are module-level globals, so
a reload starts them empty while the datablocks still carry the `global_idx` /
`global_uuid` they had before. The first temp-property read afterwards has to
append a slot and write `global_idx`, and Blender refuses that write inside a
panel draw or an operator poll. Refresh the identities immediately after the
reload - the same preparation a file load performs:

```python
from qmyi.model.model_data import refresh_all_uuids

refresh_all_uuids()
for tree in (g for g in bpy.data.node_groups if g.bl_idname == "QianyiNodeTree"):
    if tree.global_uuid != -1:
        tree.get_temp_data()
        for pattern in tree.patterns:
            if pattern.global_uuid != -1:
                pattern.get_temp_data()
```

Never assign `global_idx` yourself: it is the index every reference resolves
through, and rewriting it breaks them.

## Verify after a reload

```python
import bpy
import sys
import qmyi

print(qmyi.__file__)                                     # module actually in use
print(len([n for n in sys.modules if n.startswith("qmyi")]), "qmyi modules")
print([h.__name__ for h in bpy.app.handlers.load_post])  # persistent handlers, no duplicates
```

## Alternatives and limits

- `qmyi.utilities.register.cleanse_modules("qmyi")` drops every `qmyi*` module
  from `sys.modules`; re-importing afterwards is the most thorough reload when a
  submodule rename or a stale class identity confuses the simpler path.
- A class that fails to unregister leaves a stale registration in `bpy.types`;
  that is the one case that still needs a Blender restart.
