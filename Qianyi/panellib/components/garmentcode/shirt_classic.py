"""Non-fitted shirt preset (right half), from GarmentCode's ``bodice.py``.

Source classes: ``Shirt`` (the ``fitted=False`` path), composed from
``tee.TorsoFrontHalfPanel`` / ``TorsoBackHalfPanel``, ``ArmholeCurve``,
``SleevePanel`` and the collar components. Mirror the right half for the left.
"""

from __future__ import annotations

import math

from ._common import lerp
from ._kernel import segment_length
from .shirt import SCHEMA as _FITTED_SCHEMA
from .shirt import compose_shirt
from .tee_torso import (back_half_segments, back_values, back_width_at,
                        front_half_segments, front_values, front_width_at)

COMPONENT_ID = "gc_shirt"
VERSION = 1
LABEL = "GC Shirt (Right Half)"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode Shirt: right straight torso half with sleeve and "
               "collar openings cut in, plus sleeve and collar panels.")

_FITTED_PARAMS = _FITTED_SCHEMA["params"]
_SHARED_KEYS = (
    "shoulder_w", "neck_w", "connecting_width", "sleeveless", "armhole_shape",
    "sleeve_angle", "sleeve_length", "end_width", "opening_dir_mix",
    "standing_shoulder", "standing_shoulder_len", "smoothing_coeff",
    "arm_length", "wrist", "collar_kind", "collar_width", "front_neck_depth",
    "back_neck_depth", "neckline_angle", "flip_curve", "collar_style",
    "collar_depth", "lapel_standing", "head_l", "hood_length", "hood_depth",
)

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": dict(
        {key: _FITTED_PARAMS[key] for key in _SHARED_KEYS},
        **{
            "bust": {"type": "float", "unit": "cm", "min": 50.0, "max": 200.0,
                     "default": 99.8407, "label": "Bust"},
            "back_width": {"type": "float", "unit": "cm", "min": 20.0, "max": 100.0,
                           "default": 47.6761, "label": "Back Width"},
            "shoulder_incl": {"type": "float", "unit": "deg", "min": 0.0, "max": 60.0,
                              "default": 21.6777, "label": "Shoulder Inclination"},
            "waist_line": {"type": "float", "unit": "cm", "min": 10.0, "max": 80.0,
                           "default": 36.8913, "label": "Waist Line"},
            "shirt_width": {"type": "float", "unit": "x", "min": 0.5, "max": 2.0,
                            "default": 1.05, "label": "Shirt Width"},
            "shirt_flare": {"type": "float", "unit": "x", "min": 0.5, "max": 3.0,
                            "default": 1.0, "label": "Shirt Flare"},
            "shirt_length": {"type": "float", "unit": "x", "min": 0.2, "max": 5.0,
                             "default": 1.2, "label": "Shirt Length"},
            "bust_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                          "default": 25.6947, "label": "Bust Line"},
            "vert_bust_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                               "default": 21.1388, "label": "Vertical Bust Line"},
        },
    ),
}

_TEE_KEYS = ("bust", "back_width", "shoulder_incl", "waist_line",
             "shirt_width", "shirt_flare", "shirt_length")


def build(params: dict):
    tee_params = {key: params[key] for key in _TEE_KEYS}
    front = front_half_segments(tee_params)
    back = back_half_segments(tee_params)

    shoulder_w = float(params["shoulder_w"])
    shoulder_inclination = float(params["shoulder_incl"])
    base_sleeve_balance = shoulder_w - 2.0
    minimum_collar = float(params["neck_w"])
    maximum_collar = base_sleeve_balance - 2.0
    collar_width_fraction = float(params["collar_width"])
    collar_width = lerp(minimum_collar, maximum_collar, collar_width_fraction) \
        if collar_width_fraction >= 0.0 \
        else lerp(0.0, minimum_collar, 1.0 + collar_width_fraction)

    connecting_width = float(params["connecting_width"])
    front_armhole_width = front_width_at(tee_params, connecting_width)
    back_armhole_width = back_width_at(tee_params, connecting_width)

    shoulder_tan = math.tan(math.radians(shoulder_inclination))
    body_bust_line = (2.0 / 3.0) * float(params["vert_bust_line"]) \
        + (1.0 / 3.0) * float(params["bust_line"])
    # The straight torso's ``get_width(0)`` is the panel's own width.
    front_panel_width = front_values(tee_params)[0]
    back_panel_width = back_values(tee_params)[0]
    front_adjustment = shoulder_tan * (front_panel_width - collar_width / 2.0)
    back_adjustment = shoulder_tan * (back_panel_width - collar_width / 2.0)
    front_max = segment_length(front[-1]) - shoulder_tan * front_panel_width - 1.0
    back_max = segment_length(back[-1]) - shoulder_tan * back_panel_width - 1.0
    front_depth = min(float(params["front_neck_depth"]) * body_bust_line, front_max) \
        + front_adjustment
    back_depth = min(float(params["back_neck_depth"]) * body_bust_line, back_max) \
        + back_adjustment

    return compose_shirt(front, back, front_armhole_width, back_armhole_width,
                         collar_width, front_depth, back_depth, params,
                         front_name="torso_front_half", back_name="torso_back_half")
