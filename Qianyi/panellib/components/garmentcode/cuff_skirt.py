"""Cuff skirt preset, transcribed from GarmentCode's ``bands.py``.

Source class: ``CuffSkirt`` (two flared, gathered ``SkirtPanel`` pieces).
"""

from __future__ import annotations

from .skirt_panel import skirt_panel_spec
from ._common import name_side_edges

COMPONENT_ID = "gc_cuff_skirt"
VERSION = 1
LABEL = "GC Cuff Skirt"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode CuffSkirt: two flared, gathered cuff pieces."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {"type": "float", "unit": "cm", "min": 4.0, "max": 80.0,
                  "default": 20.0, "label": "Cuff Width"},
        "length": {"type": "float", "unit": "cm", "min": 1.0, "max": 60.0,
                   "default": 8.0, "label": "Cuff Length"},
        "ruffle": {"type": "float", "unit": "x", "min": 1.0, "max": 3.0,
                   "default": 1.2, "label": "Ruffles"},
        "flare": {"type": "float", "unit": "x", "min": 1.0, "max": 3.0,
                  "default": 1.4, "label": "Flare"},
    },
}


def build(params: dict):
    width = float(params["width"])
    length = float(params["length"])
    flare_difference = (float(params["flare"]) - 1.0) * width / 2.0
    return [
        name_side_edges(skirt_panel_spec("cuff_skirt_front", width / 2.0, length,
                                         float(params["ruffle"]), flare_difference, 0.0)),
        name_side_edges(skirt_panel_spec("cuff_skirt_back", width / 2.0, length,
                                         float(params["ruffle"]), flare_difference, 0.0)),
    ]


def seams(params: dict, panels):
    """The two side seams of the cuff skirt."""
    return [
        ("cuff_skirt_front", "right", "cuff_skirt_back", "right"),
        ("cuff_skirt_front", "left", "cuff_skirt_back", "left"),
    ]
