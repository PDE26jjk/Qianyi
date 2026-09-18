"""Fitted waistband preset, transcribed from GarmentCode's ``bands.py``.

Source classes: ``FittedWB`` and ``CircleArcPanel``. The two panels follow
the body curvature with circular arcs. Only panel geometry is ported.
"""

from __future__ import annotations

from ._common import lerp, name_side_edges
from ._panels import circle_arc_from_all_length

COMPONENT_ID = "gc_fitted_wb"
VERSION = 1
LABEL = "GC Fitted Waistband"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode FittedWB: two arc waistband panels that follow the "
               "body curvature.")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "waist": {"type": "float", "unit": "cm", "min": 40.0, "max": 200.0,
                  "default": 84.3338, "label": "Waist"},
        "waist_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 120.0,
                             "default": 39.1358, "label": "Back Waist Width"},
        "hips": {"type": "float", "unit": "cm", "min": 50.0, "max": 220.0,
                 "default": 103.478, "label": "Hips"},
        "hip_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 140.0,
                           "default": 54.8237, "label": "Back Hip Width"},
        "hips_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                      "default": 23.4837, "label": "Hip Line"},
        "waist_ease": {"type": "float", "unit": "x", "min": 0.5, "max": 2.0,
                       "default": 1.0, "label": "Waist Ease"},
        "band_width": {"type": "float", "unit": "fraction", "min": 0.02, "max": 0.9,
                       "default": 0.2, "label": "Band Width"},
        "rise": {"type": "float", "unit": "fraction", "min": 0.0, "max": 1.0,
                 "default": 1.0, "label": "Rise"},
    },
}


def build(params: dict):
    waist = float(params["waist"])
    waist_back_width = float(params["waist_back_width"])
    hips = float(params["hips"])
    hip_back_width = float(params["hip_back_width"])
    hips_line = float(params["hips_line"])
    waist_ease = float(params["waist_ease"])
    band_frac = float(params["band_width"])
    rise = float(params["rise"])

    waist_length = waist_ease * waist
    waist_back_frac = waist_back_width / waist if waist else 0.0
    hips_length = hips * waist_ease
    hips_back_frac = hip_back_width / hips if hips else 0.0

    if rise + band_frac > 1.0:
        rise = 1.0 - band_frac
    top_width = lerp(hips_length, waist_length, rise + band_frac)
    top_back_fraction = lerp(hips_back_frac, waist_back_frac, rise + band_frac)
    bottom_width = lerp(hips_length, waist_length, rise)
    bottom_back_fraction = lerp(hips_back_frac, waist_back_frac, rise)
    depth = band_frac * hips_line

    return [
        name_side_edges(circle_arc_from_all_length(
            "wb_front", depth, top_width * (1.0 - top_back_fraction),
            bottom_width * (1.0 - bottom_back_fraction))),
        name_side_edges(circle_arc_from_all_length(
            "wb_back", depth, top_width * top_back_fraction,
            bottom_width * bottom_back_fraction)),
    ]


def seams(params: dict, panels):
    """The two side seams of the fitted waistband."""
    return [
        ("wb_front", "right", "wb_back", "right"),
        ("wb_front", "left", "wb_back", "left"),
    ]
