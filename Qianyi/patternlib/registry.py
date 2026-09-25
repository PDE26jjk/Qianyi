"""Component registry.

Built-in components are discovered automatically: drop a module that declares
``COMPONENT_ID`` anywhere under the ``components`` package (subfolders are
scanned too) and it appears in the library. Helper modules without a
``COMPONENT_ID`` are ignored. Reloading re-scans both the built-in package and
the user folders.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_modules: dict[str, Any] = {}
_sources: dict[str, str] = {}
_errors: list[dict] = []


@dataclass(frozen=True)
class ComponentInfo:
    """What the UI needs to list a component."""

    component_id: str
    label: str
    category: str
    source: str
    description: str
    version: int
    params: dict


def _discover_components(package_name: str, path):
    """Module names under a package, recursively, skipping private modules."""
    for info in pkgutil.iter_modules(path, package_name + "."):
        if info.ispkg:
            try:
                package = importlib.import_module(info.name)
            except Exception as error:      # one broken package must not hide the rest
                _errors.append({"path": info.name,
                                "error": f"{type(error).__name__}: {error}",
                                "source": "builtin"})
                continue
            yield from _discover_components(info.name, package.__path__)
        elif not info.name.rsplit(".", 1)[-1].startswith("_"):
            yield info.name


def load_builtin() -> None:
    """(Re)discover every built-in component under the ``components`` package."""
    _errors[:] = [entry for entry in _errors if entry.get("source") != "builtin"]
    for component_id in [name for name, source in _sources.items() if source == "builtin"]:
        _modules.pop(component_id, None)
        _sources.pop(component_id, None)
    package = importlib.import_module(".components", __package__)
    for name in _discover_components(package.__name__, package.__path__):
        try:
            module = importlib.import_module(name)
        except Exception as error:
            _errors.append({"path": name, "error": f"{type(error).__name__}: {error}",
                            "source": "builtin"})
            continue
        if getattr(module, "COMPONENT_ID", None):
            register(module, source="builtin")


def register(module, source: str = "builtin") -> None:
    component_id = getattr(module, "COMPONENT_ID", None)
    if not component_id:
        raise ValueError(f"{module.__name__} has no COMPONENT_ID")
    _modules[component_id] = module
    _sources[component_id] = source


def errors() -> list[dict]:
    """Modules that could not be loaded, as ``{path, error}`` entries."""
    return list(_errors)


def _load_user_components(paths) -> None:
    """Load user components from ``paths`` without clearing the error list."""
    for component_id in [name for name, source in _sources.items() if source == "user"]:
        _modules.pop(component_id, None)
        _sources.pop(component_id, None)

    for path in paths or []:
        directory = Path(path).expanduser()
        if not directory.is_dir():
            _errors.append({"path": str(directory), "error": "not a directory",
                            "source": "user"})
            continue
        # Deliberate Python loop: one module import per file, per directory.
        for file in sorted(directory.rglob("*.py")):
            if file.name.startswith("_"):
                continue
            relative = file.relative_to(directory).with_suffix("")
            module_name = "qianyi_user_component_" + "_".join(relative.parts)
            try:
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec is None or spec.loader is None:
                    raise ImportError("cannot load this file as a module")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                # Executed from source instead of through the import machinery:
                # a loader compares mtime and size against its cached bytecode
                # and would happily reuse a stale module when the edited file
                # keeps the same length, which is exactly what hot reload must
                # not do.
                source = file.read_text(encoding="utf-8")
                exec(compile(source, str(file), "exec"), module.__dict__)
                register(module, source="user")
            except Exception as error:      # one broken file must not hide the rest
                sys.modules.pop(module_name, None)
                _errors.append({"path": str(file),
                                "error": f"{type(error).__name__}: {error}",
                                "source": "user"})


def load_user_components(paths) -> list[dict]:
    """Load (or reload) user components from ``paths``.

    A component module is a plain python file that declares ``COMPONENT_ID``.
    Subfolders are scanned too; a file's module name is built from its path so
    two files with the same stem in different folders do not collide.
    Reloading re-executes a module that was already loaded, so a user can edit
    a component and press reload instead of restarting Blender. Modules that
    fail are recorded with their error and the others stay usable; built-in
    components are never touched.
    """
    _errors.clear()
    _load_user_components(paths)
    return errors()


def reload_all(paths=None) -> list[dict]:
    """Re-scan the built-in package and the user folders."""
    _errors.clear()
    load_builtin()
    _load_user_components(paths)
    return errors()


def get(component_id: str):
    if not _modules:
        load_builtin()
    module = _modules.get(component_id)
    if module is None:
        raise KeyError(f"unknown pattern component '{component_id}'")
    return module


def component_ids() -> list[str]:
    if not _modules:
        load_builtin()
    return sorted(_modules)


def infos() -> list[ComponentInfo]:
    result = []
    for component_id in component_ids():
        module = _modules[component_id]
        result.append(ComponentInfo(
            component_id=component_id,
            label=getattr(module, "LABEL", component_id),
            category=getattr(module, "CATEGORY", "Other"),
            source=_sources.get(component_id, "builtin"),
            description=getattr(module, "DESCRIPTION", ""),
            version=int(getattr(module, "VERSION", 1)),
            params=getattr(module, "SCHEMA", {}).get("params", {}),
        ))
    return result


def info(component_id: str) -> ComponentInfo:
    module = get(component_id)
    return ComponentInfo(
        component_id=component_id,
        label=getattr(module, "LABEL", component_id),
        category=getattr(module, "CATEGORY", "Other"),
        source=_sources.get(component_id, "builtin"),
        description=getattr(module, "DESCRIPTION", ""),
        version=int(getattr(module, "VERSION", 1)),
        params=getattr(module, "SCHEMA", {}).get("params", {}),
    )


def default_params(component_id: str) -> dict:
    module = get(component_id)
    schema = getattr(module, "SCHEMA", {})
    return {name: spec.get("default") for name, spec in schema.get("params", {}).items()}
