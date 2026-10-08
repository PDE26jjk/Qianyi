## Why

Blender reports an add-on that writes a module into `sys.modules` under a name
of its own as a policy violation: the module's file lives inside the extension
directory while its name is not part of the extension's package.
`qyapi.register()` published the script surface as a top-level `qyapi`, plus one
entry per sub-module, so an installed copy listed
`Policy violation with top level module: qyapi` and a line per sub-module in its
add-on window. The surface has to be reachable without publishing that name.

## What Changes

- **BREAKING** for script clients: `import qyapi` no longer resolves. The
  surface is imported from the registered add-on package instead, whose name
  carries the repository the add-on was installed from.
- `qyapi.register()` publishes nothing and `unregister()` takes nothing back,
  so registering the add-on leaves `sys.modules` as it found it.
- The requirement's scenarios are restated in terms of that import, and a
  scenario pins that no bare module name is published.
- The recipe is carried by the module docstring and `docs/agent-api.md`, and the
  probe asserts it.

## Capabilities

### New Capabilities

(none - the surface and its entry points do not change)

### Modified Capabilities

- `agent-scripting-surface`: the surface is reached as a sub-module of whichever
  add-on package is registered instead of under a name the add-on publishes, and
  the add-on MUST NOT create a top-level module name.

## Impact

- `Qianyi/qyapi/__init__.py` (register/unregister and the module docstring).
- `docs/agent-api.md` and `tools/probe_agent_api.py`.
- Script clients: a notebook or probe that wrote `import qyapi` imports the
  add-on package and takes `qyapi` from it.
- Nothing else: the entry points, their arguments, the undo behaviour and the
  simulation payload are untouched.
