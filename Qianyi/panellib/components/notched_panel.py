"""A panel whose own parameter changes its edge list: the hook's test case."""

from __future__ import annotations

from ..curves import Line
from ..spec import EdgeSpec, PanelSpec

COMPONENT_ID = "notched_panel"
VERSION = 1
LABEL = "Notched Panel"
CATEGORY = "Panels"
DESCRIPTION = "A rectangle whose top edge gains a notch when notch depth is set."

# A notch shallower than this counts as no notch. Two reasons: a threshold of
# "greater than zero" makes the edge list flip between 4 and 8 edges while the
# slider sits near zero, and a very shallow notch puts its two vertical edges
# closer together than the mesh stage's own de-duplication distance
# (granularity * 0.02, 0.4 mm at the default 20 mm), which it cannot mesh.
MIN_NOTCH_DEPTH = 1.0

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {"type": "float", "unit": "mm", "min": 20.0, "max": 2000.0,
                  "default": 300.0, "label": "Width"},
        "height": {"type": "float", "unit": "mm", "min": 20.0, "max": 2000.0,
                   "default": 400.0, "label": "Height"},
        "notch_depth": {"type": "float", "unit": "mm", "min": 0.0, "max": 150.0,
                        "default": 0.0, "label": "Notch Depth"},
    },
}


def build(params: dict) -> list[PanelSpec]:
    width = float(params["width"])
    height = float(params["height"])
    depth = float(params.get("notch_depth", 0.0))

    if depth < MIN_NOTCH_DEPTH:
        vertices = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
        edges = [
            EdgeSpec(0, 1, Line(), name="hem"),
            EdgeSpec(1, 2, Line(), name="side_right"),
            EdgeSpec(2, 3, Line(), name="top"),
            EdgeSpec(3, 0, Line(), name="side_left"),
        ]
        return [PanelSpec(name="notched", vertices=vertices, edges=edges)]

    # A notch replaces the straight top edge with three edges, so the panel's
    # edge list changes whenever the notch is switched on or off.
    vertices = [
        (0.0, 0.0), (width, 0.0), (width, height),
        (width * 0.6, height), (width * 0.6, height - depth),
        (width * 0.4, height - depth), (width * 0.4, height),
        (0.0, height),
    ]
    edges = [
        EdgeSpec(0, 1, Line(), name="hem"),
        EdgeSpec(1, 2, Line(), name="side_right"),
        EdgeSpec(2, 3, Line(), name="top_right"),
        EdgeSpec(3, 4, Line(), name="notch_right"),
        EdgeSpec(4, 5, Line(), name="notch_bottom"),
        EdgeSpec(5, 6, Line(), name="notch_left"),
        EdgeSpec(6, 7, Line(), name="top_left"),
        EdgeSpec(7, 0, Line(), name="side_left"),
    ]
    return [PanelSpec(name="notched", vertices=vertices, edges=edges)]
