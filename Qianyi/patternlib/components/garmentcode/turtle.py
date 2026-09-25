"""Turtleneck collar preset, transcribed from GarmentCode's ``collars.py``.

Source class: ``Turtle`` (two straight band panels sized from the neckline
arc lengths).
"""

from __future__ import annotations

from ._common import name_side_edges, polygon_cm
from ._collar import chain_length, neckline_half

COMPONENT_ID = "gc_turtle"
VERSION = 1
LABEL = "GC Turtleneck Collar"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode Turtle: front and back turtleneck collar panels."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                  "default": 18.0, "label": "Collar Width"},
        "depth": {"type": "float", "unit": "cm", "min": 2.0, "max": 40.0,
                  "default": 12.0, "label": "Collar Depth"},
        "front_neck_depth": {"type": "float", "unit": "cm", "min": 1.0, "max": 30.0,
                             "default": 8.0, "label": "Front Neck Depth"},
        "back_neck_depth": {"type": "float", "unit": "cm", "min": 1.0, "max": 30.0,
                            "default": 5.0, "label": "Back Neck Depth"},
    },
}


def _band(name, width, depth):
    return polygon_cm(name, [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)])


def build(params: dict):
    width = float(params["width"])
    depth = float(params["depth"])
    front_length = chain_length(neckline_half("Circle", float(params["front_neck_depth"]), width))
    back_length = chain_length(neckline_half("Circle", float(params["back_neck_depth"]), width))
    return [name_side_edges(_band("collar_front", front_length, depth)),
            name_side_edges(_band("collar_back", back_length, depth))]


def seams(params: dict, panels):
    """The two side seams of the turtleneck band."""
    return [
        ("collar_front", "right", "collar_back", "right"),
        ("collar_front", "left", "collar_back", "left"),
    ]
