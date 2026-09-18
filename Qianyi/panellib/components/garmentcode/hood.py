"""Hood preset, transcribed from GarmentCode's ``collars.py`` (``HoodPanel``).

The mirrored two-panel hood of ``Hood2Panels`` is one panel here; mirror it for
the other side.
"""

from __future__ import annotations

from ._common import CM_TO_MM
from ._collar import chain_length, hood_spec, neckline_half
from ._kernel import segments_to_panel

COMPONENT_ID = "gc_hood"
VERSION = 1
LABEL = "GC Hood Panel"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode HoodPanel: one hood side; mirror it for the other side."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                  "default": 18.0, "label": "Collar Width"},
        "front_depth": {"type": "float", "unit": "cm", "min": 2.0, "max": 40.0,
                        "default": 8.0, "label": "Front Neck Depth"},
        "back_depth": {"type": "float", "unit": "cm", "min": 2.0, "max": 40.0,
                       "default": 5.0, "label": "Back Neck Depth"},
        "head_l": {"type": "float", "unit": "cm", "min": 10.0, "max": 40.0,
                   "default": 26.3262, "label": "Head Length"},
        "hood_length": {"type": "float", "unit": "x", "min": 0.5, "max": 1.5,
                        "default": 1.0, "label": "Hood Length"},
        "hood_depth": {"type": "float", "unit": "x", "min": 0.5, "max": 2.0,
                       "default": 1.0, "label": "Hood Depth"},
    },
}


def build(params: dict):
    width = float(params["width"])
    front_length = chain_length(neckline_half("Circle", float(params["front_depth"]), width))
    back_length = chain_length(neckline_half("Circle", float(params["back_depth"]), width))
    inside_length = float(params["head_l"]) * float(params["hood_length"])
    depth = width / 2.0 * float(params["hood_depth"])
    segments = hood_spec("hood", float(params["front_depth"]), float(params["back_depth"]),
                         front_length, back_length, width, inside_length, depth)
    return [segments_to_panel("hood", segments, scale=CM_TO_MM)]
