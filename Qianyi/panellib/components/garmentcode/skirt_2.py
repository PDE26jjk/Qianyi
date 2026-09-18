"""Two-panel skirt preset, transcribed from GarmentCode's ``skirt_paneled.py``.

Source class: ``Skirt2`` (two ``SkirtPanel`` pieces). Only panel geometry is
ported.
"""

from __future__ import annotations

from ._common import lerp, name_side_edges
from .skirt_panel import skirt_panel_spec

COMPONENT_ID = "gc_skirt_2"
VERSION = 1
LABEL = "GC Two-Panel Skirt"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode Skirt2: front and back flared skirt panels."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "hips": {"type": "float", "unit": "cm", "min": 50.0, "max": 220.0,
                 "default": 103.478, "label": "Hips"},
        "hip_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 140.0,
                           "default": 54.8237, "label": "Back Hip Width"},
        "waist": {"type": "float", "unit": "cm", "min": 40.0, "max": 200.0,
                  "default": 84.3338, "label": "Waist"},
        "waist_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 120.0,
                             "default": 39.1358, "label": "Back Waist Width"},
        "hips_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                      "default": 23.4837, "label": "Hip Line"},
        "leg_length": {"type": "float", "unit": "cm", "min": 20.0, "max": 150.0,
                       "default": 85.2888, "label": "Leg Length"},
        "rise": {"type": "float", "unit": "fraction", "min": 0.5, "max": 1.0,
                 "default": 1.0, "label": "Rise"},
        "ruffle": {"type": "float", "unit": "x", "min": 1.0, "max": 2.0,
                   "default": 1.3, "label": "Waist Ruffles"},
        "skirt_length": {"type": "float", "unit": "x", "min": -0.2, "max": 0.95,
                         "default": 0.2, "label": "Length"},
        "flare": {"type": "float", "unit": "cm", "min": 0.0, "max": 20.0,
                  "default": 0.0, "label": "Flare"},
        "bottom_cut": {"type": "float", "unit": "x", "min": 0.0, "max": 0.9,
                       "default": 0.0, "label": "Bottom Cut"},
    },
}


def build(params: dict):
    hips = float(params["hips"])
    hip_back_width = float(params["hip_back_width"])
    waist = float(params["waist"])
    waist_back_width = float(params["waist_back_width"])
    hips_line = float(params["hips_line"])
    leg_length = float(params["leg_length"])
    rise = float(params["rise"])
    skirt_length = float(params["skirt_length"])
    ruffle = float(params["ruffle"])
    flare = float(params["flare"])

    adjusted_waist = lerp(hips, waist, rise)
    adjusted_hips_depth = rise * hips_line
    adjusted_back_waist = lerp(hip_back_width, waist_back_width, rise)
    length = max(adjusted_hips_depth + skirt_length * leg_length, 5.0)
    # GarmentCode multiplies the cut fraction by the length fraction, not by
    # the evaluated length; keep that quirk.
    bottom_cut = float(params["bottom_cut"]) * skirt_length

    return [
        name_side_edges(skirt_panel_spec("skirt_front", adjusted_waist - adjusted_back_waist,
                                         length, ruffle, flare, bottom_cut)),
        name_side_edges(skirt_panel_spec("skirt_back", adjusted_back_waist,
                                         length, ruffle, flare, bottom_cut)),
    ]


def seams(params: dict, panels):
    """The two side seams of the two-panel skirt."""
    return [
        ("skirt_front", "right", "skirt_back", "right"),
        ("skirt_front", "left", "skirt_back", "left"),
    ]
