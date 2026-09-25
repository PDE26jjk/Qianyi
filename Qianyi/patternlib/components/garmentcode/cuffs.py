"""Cuff band preset, transcribed from GarmentCode's ``bands.py``.

Source class: ``CuffBand`` (two ``StraightBandPanel`` pieces).
"""

from __future__ import annotations

from ._common import name_side_edges, polygon_cm
COMPONENT_ID = "gc_cuff_band"
VERSION = 1
LABEL = "GC Cuff Band"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode CuffBand: two straight cuff pieces."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {"type": "float", "unit": "cm", "min": 4.0, "max": 80.0,
                  "default": 20.0, "label": "Cuff Width"},
        "length": {"type": "float", "unit": "cm", "min": 1.0, "max": 60.0,
                   "default": 8.0, "label": "Cuff Length"},
    },
}


def _straight(name, width, depth):
    return polygon_cm(name, [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)])


def build(params: dict):
    half = float(params["width"]) / 2.0
    depth = float(params["length"])
    return [name_side_edges(_straight("cuff_front", half, depth)),
            name_side_edges(_straight("cuff_back", half, depth))]


def seams(params: dict, panels):
    """The two side seams of the cuff band."""
    return [
        ("cuff_front", "right", "cuff_back", "right"),
        ("cuff_front", "left", "cuff_back", "left"),
    ]
