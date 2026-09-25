"""Panel-skirt preset, transcribed from GarmentCode's ``skirt_paneled.py``.

Source class: ``ThinSkirtPanel``. Only panel geometry is ported.
"""

from __future__ import annotations

from ._gcd_panels import thin_skirt_spec

COMPONENT_ID = "gc_thin_skirt_panel"
VERSION = 1
LABEL = "GC Thin Skirt Panel"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode ThinSkirtPanel: one flared panel with an optional curved hem."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "top_width": {"type": "float", "unit": "cm", "min": 2.0, "max": 100.0,
                      "default": 10.0, "label": "Top Width"},
        "bottom_width": {"type": "float", "unit": "cm", "min": 2.0, "max": 200.0,
                         "default": 20.0, "label": "Bottom Width"},
        "length": {"type": "float", "unit": "cm", "min": 5.0, "max": 200.0,
                   "default": 70.0, "label": "Length"},
        "bottom_curvature": {"type": "float", "unit": "fraction", "min": -0.5, "max": 0.5,
                             "default": 0.0, "label": "Hem Curvature"},
    },
}


def build(params: dict):
    return [thin_skirt_spec(
        "skirt_panel",
        top_width=float(params["top_width"]),
        bottom_width=float(params["bottom_width"]),
        length=float(params["length"]),
        bottom_curvature=float(params["bottom_curvature"]),
    )]
