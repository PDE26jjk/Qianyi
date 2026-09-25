"""T-shirt torso preset, transcribed from GarmentCode's ``tee.py``.

Source classes: ``TorsoFrontHalfPanel`` and ``TorsoBackHalfPanel``.
Only the two panel geometries are ported.
"""

from __future__ import annotations

import math

from ._common import CM_TO_MM
from ._kernel import line_segment, segments_to_gcd_panel

COMPONENT_ID = "gc_tee_torso"
VERSION = 1
LABEL = "GC Tee Torso Halves"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode T-shirt front and back half panels, fitted to the "
               "bust and shoulder measurements.")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "bust": {"type": "float", "unit": "cm", "min": 50.0, "max": 200.0,
                 "default": 99.8407, "label": "Bust"},
        "back_width": {"type": "float", "unit": "cm", "min": 20.0, "max": 100.0,
                       "default": 47.6761, "label": "Back Width"},
        "shoulder_incl": {"type": "float", "unit": "deg", "min": 0.0, "max": 60.0,
                          "default": 21.6777, "label": "Shoulder Inclination"},
        "waist_line": {"type": "float", "unit": "cm", "min": 10.0, "max": 80.0,
                       "default": 36.8913, "label": "Waist Line"},
        "shirt_width": {"type": "float", "unit": "x", "min": 0.5, "max": 2.0,
                        "default": 1.0, "label": "Shirt Width"},
        "shirt_flare": {"type": "float", "unit": "x", "min": 0.5, "max": 3.0,
                        "default": 1.0, "label": "Shirt Flare"},
        "shirt_length": {"type": "float", "unit": "x", "min": 0.2, "max": 5.0,
                         "default": 1.2, "label": "Shirt Length"},
    },
}


def _shirt_values(params: dict):
    bust = float(params["bust"])
    back_width = float(params["back_width"])
    shoulder_incl = float(params["shoulder_incl"])
    waist_line = float(params["waist_line"])
    measured_width = float(params["shirt_width"]) * bust
    flare_width = float(params["shirt_flare"]) * measured_width
    shoulder_tan = math.tan(math.radians(shoulder_incl))
    base_length = float(params["shirt_length"]) * waist_line

    front_fraction = ((bust - back_width) / 2.0) / bust if bust else 0.0
    front_width = front_fraction * measured_width
    front_bottom = front_fraction * flare_width
    front_shoulder = shoulder_tan * front_width
    # The front is shortened so the shoulder line arrives at the sleeve.
    front_length = base_length - shoulder_tan * (front_fraction - (0.5 - front_fraction)) * bust

    back_fraction = (back_width / 2.0) / bust if bust else 0.0
    back_half_width = back_fraction * measured_width
    back_bottom = back_fraction * flare_width
    back_shoulder = shoulder_tan * back_half_width
    return ((front_width, front_bottom, front_length, front_shoulder),
            (back_half_width, back_bottom, base_length, back_shoulder))


def front_values(params: dict):
    """``(width, bottom_width, length, shoulder)`` of the front half."""
    return _shirt_values(params)[0]


def back_values(params: dict):
    """``(width, bottom_width, length, shoulder)`` of the back half."""
    return _shirt_values(params)[1]


def _half_segments(width, bottom_width, length, shoulder):
    # GarmentCode's loop is [0, 0] -> [-bottom, 0] -> [-width, length] ->
    # [0, length + shoulder] (clockwise); ``segments_to_gcd_panel`` reverses it.
    return [line_segment((0.0, 0.0), (-bottom_width, 0.0)),
            line_segment((-bottom_width, 0.0), (-width, length)),
            line_segment((-width, length), (0.0, length + shoulder)),
            line_segment((0.0, length + shoulder), (0.0, 0.0))]


def front_half_segments(params: dict):
    return _half_segments(*front_values(params))


def back_half_segments(params: dict):
    return _half_segments(*back_values(params))


def front_width_at(params: dict, level: float) -> float:
    """GarmentCode's ``TorsoFrontHalfPanel.get_width``."""
    width, bottom_width, length, _ = front_values(params)
    return width if length <= 0 else level * (bottom_width - width) / length + width


def back_width_at(params: dict, level: float) -> float:
    """GarmentCode's ``TorsoBackHalfPanel.get_width``."""
    width, bottom_width, length, _ = back_values(params)
    return width if length <= 0 else level * (bottom_width - width) / length + width


def build(params: dict):
    return [
        segments_to_gcd_panel("torso_front_half", front_half_segments(params), scale=CM_TO_MM,
                          edge_names={1: "outside", 2: "shoulder"}),
        segments_to_gcd_panel("torso_back_half", back_half_segments(params), scale=CM_TO_MM,
                          edge_names={1: "outside", 2: "shoulder"}),
    ]


def seams(params: dict, panels):
    """The shoulder and under-arm seams of the tee torso halves."""
    return [
        ("torso_front_half", "outside", "torso_back_half", "outside"),
        ("torso_front_half", "shoulder", "torso_back_half", "shoulder"),
    ]
