"""Many-panel skirt preset, transcribed from GarmentCode's ``skirt_paneled.py``.

Source class: ``SkirtManyPanels``. The N pieces are returned as N panels;
the three-dimensional distribution around the body is not ported.
"""

from __future__ import annotations

import math

from ._common import lerp, name_side_edges
from ._gcd_panels import thin_skirt_spec

COMPONENT_ID = "gc_skirt_many_panels"
VERSION = 1
LABEL = "GC Many-Panel Skirt"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode SkirtManyPanels: N identical flared panels around the waist."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "hips": {"type": "float", "unit": "cm", "min": 50.0, "max": 220.0,
                 "default": 103.478, "label": "Hips"},
        "waist": {"type": "float", "unit": "cm", "min": 40.0, "max": 200.0,
                  "default": 84.3338, "label": "Waist"},
        "hips_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                      "default": 23.4837, "label": "Hip Line"},
        "leg_length": {"type": "float", "unit": "cm", "min": 20.0, "max": 150.0,
                       "default": 85.2888, "label": "Leg Length"},
        "rise": {"type": "float", "unit": "fraction", "min": 0.5, "max": 1.0,
                 "default": 1.0, "label": "Rise"},
        "skirt_length": {"type": "float", "unit": "x", "min": -0.2, "max": 0.95,
                         "default": 0.2, "label": "Length"},
        "suns": {"type": "float", "unit": "x", "min": 0.1, "max": 1.95,
                 "default": 0.75, "label": "Suns"},
        "n_gcd_panels": {"type": "int", "unit": "panels", "min": 4, "max": 15,
                     "default": 4, "label": "Panels"},
        "panel_curve": {"type": "float", "unit": "fraction", "min": -0.35, "max": 0.0,
                        "default": 0.0, "label": "Panel Curve"},
    },
}


def build(params: dict):
    hips = float(params["hips"])
    waist = float(params["waist"])
    hips_line = float(params["hips_line"])
    leg_length = float(params["leg_length"])
    rise = float(params["rise"])
    suns = float(params["suns"])
    n_gcd_panels = max(1, int(round(float(params["n_gcd_panels"]))))

    adjusted_waist = lerp(hips, waist, rise)
    adjusted_hips_depth = rise * hips_line
    length = max(adjusted_hips_depth + float(params["skirt_length"]) * leg_length, 5.0)
    panel_width = adjusted_waist / n_gcd_panels
    flare = 1.0 + suns * length * 2.0 * math.pi / adjusted_waist
    bottom_width = panel_width * flare

    # Deliberate comprehension: one PatternSpec per panel, a list of Python
    # objects that numpy cannot build.
    return [name_side_edges(thin_skirt_spec(
                f"skirt_panel_{index}", panel_width, bottom_width,
                length, float(params["panel_curve"])))
            for index in range(n_gcd_panels)]


def seams(params: dict, panels):
    """Sew the N identical panels into a ring, left to the next right."""
    count = len(panels)
    return [
        (f"skirt_panel_{index}", "left",
         f"skirt_panel_{(index + 1) % count}", "right")
        for index in range(count)
    ]
