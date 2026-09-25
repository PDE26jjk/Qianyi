"""A waistband: two patterns joined by side seams, sized along the waist."""

from __future__ import annotations

from ..curves import Bezier, Line
from ..spec import EdgeSpec, PatternSpec

COMPONENT_ID = "waistband"
VERSION = 1
LABEL = "Waistband"
CATEGORY = "Bands"
DESCRIPTION = "Front and back band patterns sized from the waist length."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "waist_length": {
            "type": "float", "unit": "mm", "min": 100.0, "max": 2000.0,
            "default": 800.0, "label": "Waist Length",
        },
        "height": {
            "type": "float", "unit": "mm", "min": 10.0, "max": 300.0,
            "default": 60.0, "label": "Height",
        },
        "waist_curve": {
            "type": "float", "unit": "mm", "min": 0.0, "max": 100.0,
            "default": 10.0, "label": "Waist Curve",
        },
    },
}


def _band(name: str, width: float, height: float, curve: float) -> PatternSpec:
    # Counter-clockwise: down the left side, along the bottom, up the right
    # side, then back along the waist edge. The first vertex is the reference
    # point and stays put for every parameter combination.
    vertices = [(0.0, 0.0), (0.0, -height), (width, -height), (width, 0.0)]
    if curve > 1e-6:
        top = Bezier(controls=((width / 2.0, curve),))
    else:
        top = Line()
    edges = [
        EdgeSpec(0, 1, Line(), name="side_left"),
        EdgeSpec(1, 2, Line(), name="bottom"),
        EdgeSpec(2, 3, Line(), name="side_right"),
        EdgeSpec(3, 0, top, name="waist"),
    ]
    return PatternSpec(name=name, vertices=vertices, edges=edges)


def build(params: dict) -> list[PatternSpec]:
    waist_length = float(params["waist_length"])
    height = float(params["height"])
    curve = float(params.get("waist_curve", 0.0))
    half = waist_length / 2.0
    return [
        _band("band_front", half, height, curve),
        _band("band_back", half, height, curve),
    ]
