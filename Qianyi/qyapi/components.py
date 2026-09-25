"""The pattern component library, without a scene in the way.

A component turns a parameter block into patterns. Building one here returns the
outlines, the edge labels and the outline check, and changes nothing - which is
the loop to use when writing a component: build it, look at the outlines, then
put a generator into the project with it.
"""

from __future__ import annotations

import numpy as np

from . import _address as address
from .errors import QyapiError
from ..model.pattern import boundary_self_intersection
from ..patternlib import component, registry
from ..patternlib.land import land_pattern


def list():  # noqa: A001 - the surface's name for this call
    """Every component the library offers, with its parameter schema."""
    _ensure_registered()
    return address.jsonify({"components": [_entry(info) for info in registry.infos()]})


def info(component_id):
    """One component's entry."""
    _ensure_registered()
    return address.jsonify(_entry(_info_or_refuse(component_id)))


def build(component_id, params=None):
    """Build a component and return its outlines; the scene is untouched."""
    _ensure_registered()
    info = _info_or_refuse(component_id)
    values = _known_params(info, params)
    try:
        spec = component.build_component(component_id, values)
    except Exception as error:
        raise QyapiError(f"component {component_id!r} could not be built: {error}",
                         ("its parameters may not describe a pattern",
                          "qyapi.components.info() has the schema")) from error
    patterns = []
    for pattern in spec.patterns:  # loop: one landed pattern per output
        landed = land_pattern(pattern)
        outline = [[float(point[0]), float(point[1])] for point in landed.vertices]
        boundary = [outline[edge.v0] for edge in landed.edges]
        intersected, crossing = boundary_self_intersection(
            np.asarray(boundary, dtype="float32"))
        patterns.append({
            "name": landed.name,
            "vertices": len(landed.vertices),
            "edges": [{"index": index, "label": edge.name or None, "kind": edge.kind,
                       "v0": edge.v0, "v1": edge.v1, "sewable": edge.sewable}
                      for index, edge in enumerate(landed.edges)],
            "outline": outline,
            "valid": not intersected,
            "crossing": None if crossing is None
            else [float(crossing[0]), float(crossing[1])],
        })
    return address.jsonify({"component": component_id, "params": spec.params,
                            "patterns": patterns})


def reload():
    """Re-read the built-in components and the user folders."""
    from .. import preferences

    errors = registry.reload_all(preferences.component_paths())
    return address.jsonify({"loaded": len(registry.infos()), "errors": errors})


# --- internals -------------------------------------------------------------

def _ensure_registered():
    if not registry.infos():
        registry.load_builtin()


def _entry(info):
    return {
        "id": info.component_id,
        "label": info.label,
        "category": info.category,
        "source": info.source,
        "description": info.description,
        "version": info.version,
        "params": info.params,
    }


def _info_or_refuse(component_id):
    try:
        return registry.info(component_id)
    except Exception as error:
        ids = ", ".join(info.component_id for info in registry.infos())
        raise QyapiError(f"no component named {component_id!r}",
                         (f"components: {ids}",)) from error


def _known_params(info, params):
    values = dict(params or {})
    unknown = sorted(set(values) - set(info.params))
    if unknown:
        raise QyapiError(f"component {info.component_id!r} has no parameter "
                         f"{', '.join(unknown)}",
                         (f"parameters: {', '.join(info.params)}",))
    return values
