"""Straight waistband preset, transcribed from GarmentCode's ``bands.py``.

Source classes: ``StraightWB`` and ``StraightBandPanel``.
Only the two panel geometries are ported; the stitching rules and placement
are intentionally left out.
"""

from __future__ import annotations

from ._common import lerp, name_side_edges, polygon_cm

COMPONENT_ID = "gc_straight_wb"
VERSION = 1
LABEL = "GC Straight Waistband"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode StraightWB: two straight waistband panels sized "
               "from waist and hip measurements.")

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


def _band(name: str, width_cm: float, depth_cm: float):
    # GarmentCode's loop is [0, 0] -> [0, depth] -> [width, depth] -> [width, 0]
    # (clockwise); this is the same rectangle counter-clockwise.
    return polygon_cm(name, [(0.0, 0.0), (width_cm, 0.0),
                             (width_cm, depth_cm), (0.0, depth_cm)])


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

    # GarmentCode clamps the rise so the band still sits on the body.
    if rise + band_frac > 1.0:
        rise = 1.0 - band_frac
    top_width = lerp(hips_length, waist_length, rise + band_frac)
    top_back_fraction = lerp(hips_back_frac, waist_back_frac, rise + band_frac)
    depth = band_frac * hips_line

    back_width = top_width * top_back_fraction
    front_width = top_width - back_width
    return [
        name_side_edges(_band("wb_front", front_width, depth)),
        name_side_edges(_band("wb_back", back_width, depth)),
    ]


def seams(params: dict, panels):
    """The two side seams of the straight waistband."""
    return [
        ("wb_front", "right", "wb_back", "right"),
        ("wb_front", "left", "wb_back", "left"),
    ]
