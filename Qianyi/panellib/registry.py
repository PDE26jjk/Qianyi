"""Component registry.

The library panel lists whatever this registry exposes, so adding a component
is one entry below plus its module.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Module names relative to this package, so the registry also works when the
# library is imported outside Blender.
BUILTIN_COMPONENTS = (
    ".components.square",
    ".components.waistband",
    ".components.notched_panel",
    ".components.pleated_panel",
)

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


def load_builtin() -> None:
    for name in BUILTIN_COMPONENTS:
        module = importlib.import_module(name, __package__)
        register(module)


def register(module, source: str = "builtin") -> None:
    component_id = getattr(module, "COMPONENT_ID", None)
    if not component_id:
        raise ValueError(f"{module.__name__} has no COMPONENT_ID")
    _modules[component_id] = module
    _sources[component_id] = source


def errors() -> list[dict]:
    """Modules that could not be loaded, as ``{path, error}`` entries."""
    return list(_errors)


def load_user_components(paths) -> list[dict]:
    """Load (or reload) user components from ``paths``.

    A component module is a plain python file that declares ``COMPONENT_ID``.
    Reloading re-executes a module that was already loaded, so a user can edit
    a component and press reload instead of restarting Blender. Modules that
    fail are recorded with their error and the others stay usable; built-in
    components are never touched.
    """
    _errors.clear()
    for component_id in [name for name, source in _sources.items() if source == "user"]:
        _modules.pop(component_id, None)
        _sources.pop(component_id, None)

    for path in paths or []:
        directory = Path(path).expanduser()
        if not directory.is_dir():
            _errors.append({"path": str(directory), "error": "not a directory"})
            continue
        # Deliberate Python loop: one module import per file, per directory.
        for file in sorted(directory.glob("*.py")):
            if file.name.startswith("_"):
                continue
            module_name = f"qianyi_user_component_{file.stem}"
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
                _errors.append({"path": str(file), "error": f"{type(error).__name__}: {error}"})
    return errors()


def get(component_id: str):
    if not _modules:
        load_builtin()
    module = _modules.get(component_id)
    if module is None:
        raise KeyError(f"unknown panel component '{component_id}'")
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
