"""Lapel panel preset, transcribed from GarmentCode's ``collars.py``.

Source class: ``SimpleLapelPanel``. Only the panel geometry is ported; the
projection onto the bodice corner is not.
"""

from __future__ import annotations

from ._common import CM_TO_MM
from ._kernel import line_segment, quad_segment, rel_to_abs_2d, segments_to_panel

COMPONENT_ID = "gc_simple_lapel_panel"
VERSION = 1
LABEL = "GC Simple Lapel Panel"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode SimpleLapelPanel: one lapel piece with a curved outer edge."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "length": {"type": "float", "unit": "cm", "min": 5.0, "max": 100.0,
                   "default": 30.0, "label": "Length"},
        "max_depth": {"type": "float", "unit": "cm", "min": 2.0, "max": 60.0,
                      "default": 12.0, "label": "Depth"},
    },
}


def lapel_spec(name: str, length: float, max_depth: float):
    """One GarmentCode ``SimpleLapelPanel`` under the requested name."""
    depth = max_depth
    start = (depth, -length)
    end = (0.0, 0.0)
    control = rel_to_abs_2d(start, end, (0.7, 0.2))
    segments = [line_segment((0.0, 0.0), (depth, 0.0)),
                line_segment((depth, 0.0), start),
                quad_segment(start, end, control)]
    return segments_to_panel(name, segments, scale=CM_TO_MM)


def build(params: dict):
    return [lapel_spec("lapel", float(params["length"]), float(params["max_depth"]))]
