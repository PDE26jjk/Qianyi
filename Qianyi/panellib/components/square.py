"""A rectangular panel: the smallest useful component."""

from __future__ import annotations

from ..curves import Bezier, Line
from ..spec import EdgeSpec, PanelSpec

COMPONENT_ID = "square"
VERSION = 1
LABEL = "Square Panel"
CATEGORY = "Panels"
DESCRIPTION = "A rectangle with an optional outward bow on its top edge."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {
            "type": "float", "unit": "mm", "min": 10.0, "max": 2000.0,
            "default": 300.0, "label": "Width",
        },
        "height": {
            "type": "float", "unit": "mm", "min": 10.0, "max": 2000.0,
            "default": 400.0, "label": "Height",
        },
        "top_bow": {
            "type": "float", "unit": "mm", "min": 0.0, "max": 200.0,
            "default": 0.0, "label": "Top Bow",
        },
    },
}


def build(params: dict) -> list[PanelSpec]:
    width = float(params["width"])
    height = float(params["height"])
    bow = float(params.get("top_bow", 0.0))

    # Counter-clockwise loop; the first vertex is the panel's reference point
    # and stays at the origin for every parameter combination.
    vertices = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]

    if bow > 1e-6:
        top = Bezier(controls=((width * 2.0 / 3.0, height + bow),
                               (width / 3.0, height + bow)))
    else:
        top = Line()

    edges = [
        EdgeSpec(0, 1, Line(), name="hem"),
        EdgeSpec(1, 2, Line()),
        EdgeSpec(2, 3, top),
        EdgeSpec(3, 0, Line()),
    ]
    return [PanelSpec(name="square", vertices=vertices, edges=edges)]
