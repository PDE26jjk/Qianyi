## 1. Stop publishing a module name of its own

- [x] 1.1 Remove the `sys.modules` writes from `qyapi.register()` and the
  deletion loop from `qyapi.unregister()`, leaving both as documented no-ops
- [x] 1.2 Restate the module docstring's loading instructions as the package
  import, with the reason the bare name is gone
- [x] 1.3 Verify that registering the add-on leaves `sys.modules` without a
  top-level `qyapi` entry and without the `qyapi.<sub>` entries

## 2. Carry the recipe to clients

- [x] 2.1 Rewrite the "Loading it" section of `docs/agent-api.md` and the two
  worked examples that opened with `import qyapi`
- [x] 2.2 Update `tools/probe_agent_api.py` to import the surface from the loaded
  package and to assert that no top-level name was published

## 3. Verify

- [x] 3.1 Verify the surface imports from the add-on package in a background
  session and that `help()` and `state()` answer
- [x] 3.2 Verify an installed copy reports no policy violation: the add-on
  window's warning list is empty
- [x] 3.3 Verify `tools/probe_agent_api.py` passes in full (70 checks)
