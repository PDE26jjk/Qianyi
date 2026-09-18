"""Asymmetric circle skirt preset, transcribed from ``circle_skirt.py``.

Source classes: ``AsymmSkirtCircle`` and ``AsymHalfCirclePanel``. Only panel
geometry is ported.
"""

from __future__ import annotations

import math

from ._panels import asym_half_circle_spec
from .circle_skirt import _BODY_PARAMS, _DESIGN_PARAMS, circle_length
from ._common import name_side_edges

COMPONENT_ID = "gc_asym_circle_skirt"
VERSION = 1
LABEL = "GC Asymmetric Circle Skirt"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode AsymmSkirtCircle: a longer front and a shorter back "
               "circle-skirt panel.")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": dict(_BODY_PARAMS, **_DESIGN_PARAMS, **{
        "front_length": {"type": "float", "unit": "x", "min": 0.2, "max": 2.0,
                         "default": 1.5, "label": "Front Length"},
    }),
}


def build(params: dict):
    adjusted_waist, length = circle_length(params)
    waist_radius = adjusted_waist / 2.0 / math.pi
    front_length = float(params["front_length"]) * length
    total = waist_radius * 2.0 + length + front_length
    delta_radius = total / 2.0 - front_length - waist_radius
    side_length = math.sqrt(max((total / 2.0) ** 2 - delta_radius ** 2, 0.0)) - waist_radius
    return [
        name_side_edges(asym_half_circle_spec(
            "skirt_front", waist_radius, front_length, side_length)),
        name_side_edges(asym_half_circle_spec(
            "skirt_back", waist_radius, length, side_length)),
    ]


def seams(params: dict, panels):
    """The two side seams of the asymmetric circle skirt."""
    return [
        ("skirt_front", "right", "skirt_back", "right"),
        ("skirt_front", "left", "skirt_back", "left"),
    ]
