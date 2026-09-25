"""A wide pattern with many edges: the benchmark component."""

from __future__ import annotations

import numpy as np

from ..curves import Line
from ..spec import EdgeSpec, PatternSpec

COMPONENT_ID = "pleated_pattern"
VERSION = 1
LABEL = "Pleated Pattern"
CATEGORY = "Patterns"
DESCRIPTION = "A rectangle whose top edge is folded into many teeth; used to time large patterns."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {"type": "float", "unit": "mm", "min": 50.0, "max": 5000.0,
                  "default": 1000.0, "label": "Width"},
        "height": {"type": "float", "unit": "mm", "min": 20.0, "max": 2000.0,
                   "default": 300.0, "label": "Height"},
        "teeth": {"type": "int", "min": 1, "max": 2000, "default": 10,
                  "label": "Teeth"},
        "tooth_depth": {"type": "float", "unit": "mm", "min": 0.0, "max": 200.0,
                        "default": 30.0, "label": "Tooth Depth"},
    },
}


def build(params: dict) -> list[PatternSpec]:
    width = float(params["width"])
    height = float(params["height"])
    teeth = max(1, int(params["teeth"]))
    depth = float(params.get("tooth_depth", 0.0))

    # The zigzag is built with numpy: a pattern with a thousand edges should not
    # cost a thousand interpreted steps before it is even written out.
    xs = np.linspace(0.0, width, 2 * teeth + 1)[1:-1]
    ys = np.where(np.arange(xs.size) % 2 == 0, height, height - depth)
    zigzag = np.column_stack((xs, ys))[::-1]

    vertices = [(0.0, 0.0), (width, 0.0), (width, height)]
    vertices.extend((float(point[0]), float(point[1])) for point in zigzag)
    vertices.append((0.0, height))

    edges = [
        EdgeSpec(0, 1, Line(), name="hem"),
        EdgeSpec(1, 2, Line(), name="side_right"),
    ]
    # One edge per zigzag segment, plus the closing segment to the top left.
    edges.extend(EdgeSpec(2 + index, 3 + index, Line())
                 for index in range(len(zigzag) + 1))
    edges.append(EdgeSpec(3 + len(zigzag), 0, Line(), name="side_left"))
    return [PatternSpec(name="pleated", vertices=vertices, edges=edges)]
