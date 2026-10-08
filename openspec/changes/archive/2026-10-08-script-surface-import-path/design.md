## Context

See proposal.md - Why. The add-on is installed as an extension, so its package
is named `bl_ext.<repository>.<id>` and the repository part varies with where it
was installed from (`user_default`, `blender_org`, a self-hosted repository).
A session that loaded the package by path instead, as a study notebook does,
reaches it under whatever name it loaded.

## Goals / Non-Goals

**Goals:**

- The surface stays reachable with no viewport, no operator and no active
  editor, in a background session as well as a live one.
- Registering the add-on creates no module name of its own.

**Non-Goals:**

- Keeping `import qyapi` working for an installed copy: that name is what the
  policy is about.
- Changing the entry points, their arguments, the units or the undo behaviour.

## Decisions

**Look the package up instead of naming it.** A client asks Blender for the
registered add-ons and imports the `qyapi` sub-module of the one whose key ends
in `.Qianyi`. Alternatives considered: writing out
`bl_ext.user_default.Qianyi.qyapi`, which breaks for any other repository, and
installing a helper module outside the extension directory, which writes into
the user's scripts directory and helps only sessions that have that directory.

**Publish nothing at all, rather than publishing only outside extensions.**
`register()` could skip the top-level name when `__package__` starts with
`bl_ext.`, which silences the warning while keeping the name for a session that
loaded the package by path. That leaves the shipped add-on with a documented
import that does not work where it is actually installed, which is worse than a
clear failure.

**Keep the requirement's name.** The surface is still reached under one stable
name, `qyapi`; what changes is that the name is a sub-module of the add-on
package rather than a module the add-on publishes. The delta modifies the
existing requirement instead of renaming it, so the archive merge keeps one
requirement rather than retiring one and adding another.

## Risks / Trade-offs

- [A script that was written against `import qyapi` breaks] -> the replacement is
  two lines, and all three places a client might read it from carry them.
- [A client cannot reach the preferences to find the package] -> the preferences
  are available in a background session, which the probe pins with a `-b` run.
- [The sub-module is reachable at more than one path if two copies are loaded] ->
  the same is true of the add-on itself, and the lookup names the registered
  package, so it always resolves to the enabled one.
