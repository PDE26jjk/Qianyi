"""Godet insert preset, transcribed from GarmentCode's ``godet.py``.

Source class: ``Insert``. Only the triangular insert panel is ported; the
base-skirt cuts and the many-panel distribution are separate components.
"""

from __future__ import annotations

from ._kernel import line_segment, segments_to_gcd_panel
from ._common import CM_TO_MM

COMPONENT_ID = "gc_godet_insert"
VERSION = 1
LABEL = "GC Godet Insert"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode Insert: the triangular wedge used by godet skirts."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {"type": "float", "unit": "cm", "min": 2.0, "max": 100.0,
                  "default": 30.0, "label": "Width"},
        "depth": {"type": "float", "unit": "cm", "min": 2.0, "max": 100.0,
                  "default": 30.0, "label": "Depth"},
    },
}


def build(params: dict):
    width = float(params["width"])
    depth = float(params["depth"])
    segments = [line_segment((0.0, 0.0), (width / 2.0, depth)),
                line_segment((width / 2.0, depth), (width, 0.0)),
                line_segment((width, 0.0), (0.0, 0.0))]
    return [segments_to_gcd_panel("insert", segments, scale=CM_TO_MM)]
