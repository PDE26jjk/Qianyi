"""Circle skirt presets, transcribed from GarmentCode's ``circle_skirt.py``.

Source classes: ``SkirtCircle``, ``AsymmSkirtCircle``, ``CircleArcPanel`` and
``AsymHalfCirclePanel``. Only panel geometry is ported; the optional bottom
cut and placement are left out.
"""

from __future__ import annotations

import math

from ._common import lerp, name_side_edges
from ._panels import circle_arc_from_w_length_suns

_BODY_PARAMS = {
    "hips": {"type": "float", "unit": "cm", "min": 50.0, "max": 220.0,
             "default": 103.478, "label": "Hips"},
    "waist": {"type": "float", "unit": "cm", "min": 40.0, "max": 200.0,
              "default": 84.3338, "label": "Waist"},
    "hips_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                  "default": 23.4837, "label": "Hip Line"},
    "leg_length": {"type": "float", "unit": "cm", "min": 20.0, "max": 150.0,
                   "default": 85.2888, "label": "Leg Length"},
}

_DESIGN_PARAMS = {
    "rise": {"type": "float", "unit": "fraction", "min": 0.5, "max": 1.0,
             "default": 1.0, "label": "Rise"},
    "skirt_length": {"type": "float", "unit": "x", "min": -0.2, "max": 0.95,
                     "default": 0.2, "label": "Length"},
}

COMPONENT_ID = "gc_circle_skirt"
VERSION = 1
LABEL = "GC Circle Skirt"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode SkirtCircle: symmetric front and back circle-skirt panels."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": dict(_BODY_PARAMS, **_DESIGN_PARAMS, **{
        "suns": {"type": "float", "unit": "x", "min": 0.1, "max": 1.95,
                 "default": 0.75, "label": "Suns"},
    }),
}

def circle_length(params):
    """Shared ``eval_rise`` + length evaluation for both circle skirts."""
    hips = float(params["hips"])
    waist = float(params["waist"])
    hips_line = float(params["hips_line"])
    leg_length = float(params["leg_length"])
    rise = float(params["rise"])
    adjusted_waist = lerp(hips, waist, rise)
    adjusted_hips_depth = rise * hips_line
    length = adjusted_hips_depth + float(params["skirt_length"]) * leg_length
    return adjusted_waist, max(length, 5.0)


def build(params: dict):
    adjusted_waist, length = circle_length(params)
    suns = float(params["suns"])
    top_width = adjusted_waist / 2.0
    return [
        name_side_edges(circle_arc_from_w_length_suns(
            "skirt_front", length, top_width, suns / 2.0)),
        name_side_edges(circle_arc_from_w_length_suns(
            "skirt_back", length, top_width, suns / 2.0)),
    ]


def seams(params: dict, panels):
    """The two side seams of the circle skirt."""
    return [
        ("skirt_front", "right", "skirt_back", "right"),
        ("skirt_front", "left", "skirt_back", "left"),
    ]
