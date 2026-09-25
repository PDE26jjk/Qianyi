# AGENTS.md

Guidance for agents working on the Qianyi Blender add-on.

## Where an operator task may edit

An operator task - anything whose job is a tool, a command or an editor
interaction - MUST NOT edit the low-level model files without the maintainer's
explicit permission first. Those files are:

- `Qianyi/model/pattern.py`
- `Qianyi/model/sewing.py`
- `Qianyi/model/section.py`
- `Qianyi/model/internal_line.py`
- `Qianyi/model/geometry.py`
- `Qianyi/model/qianyi_project.py`
- `Qianyi/simulation/**`

What an operator task MAY do instead:

- add a switch, a status flag or a temp property in the settings layer
  (`Qianyi/model/qianyi_data.py` is `qmyi`, and a project-level temp property on
  `QianyiProject` counts as a switch as well);
- work in its own module (for example `Qianyi/model/pattern_geometry.py` and the
  files split out of it, `Qianyi/operators/_2d_*.py`, `Qianyi/workspacetools/`,
  `Qianyi/gizmos/`);
- ask for permission, naming the file and the change, and wait for it.

If a task looks like it needs a low-level change, report the finding and ask.
Do not absorb the change silently, and do not "fix" a low-level inconsistency by
rebuilding derived data from the command side either: report it, and let the
maintainer decide where it belongs.

## Comment and commit language

Code comments and every committed public file are written in English. Replies to
the maintainer are written in Chinese.

## Committing

Nothing is committed until the maintainer says "提交". A commit is never implied
by a later instruction.

## Probe scenes

Probes and tests MUST build the scene they need - `tools/make_probe_scene.py`
(`build_fixture()`) or an in-process construction of the same kind - instead of
opening a maintainer `.blend`. Files under `extracted_files/` are local,
gitignored and frozen at the version they were saved with, so they are not
fixtures and must not be a default: a probe that needs a saved scene takes an
explicit `--scene` argument and says so in its usage line.
