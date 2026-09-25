"""Fitted shirt preset (right half), transcribed from GarmentCode's ``bodice.py``.

Source classes: ``BodiceHalf`` / ``FittedShirt``, composed from
``BodiceFrontHalf``, ``BodiceBackHalf``, ``ArmholeCurve``, ``SleevePanel`` and
the collar components. The right half is produced; mirror it for the left.
"""

from __future__ import annotations

import math

from ...curves import Bezier
from ._common import CM_TO_MM, lerp
from ._collar import arc_parameters, chain_length, hood_spec, neckline_half
from ._kernel import (Segment, cut_corner_segments, line_segment,
                      rel_to_abs_2d, segment_length, segments_to_gcd_panel)
from ._gcd_panels import circle_arc_spec, straight_band
from .bodice import back_segments, front_segments
from .simple_lapel import lapel_spec
from .sleeve import _sleeve_panel, armhole_shapes

COMPONENT_ID = "gc_fitted_shirt"
VERSION = 1
LABEL = "GC Fitted Shirt (Right Half)"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode FittedShirt: right bodice half with sleeve and collar "
               "openings cut in, plus sleeve and collar panels.")

_BODICE_KEYS = ("bust", "back_width", "shoulder_w", "waist", "waist_back_width",
                "bust_points", "bum_points", "waist_line", "waist_over_bust_line",
                "shoulder_incl", "bust_line", "vert_bust_line")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "bust": {"type": "float", "unit": "cm", "min": 50.0, "max": 200.0,
                 "default": 99.8407, "label": "Bust"},
        "back_width": {"type": "float", "unit": "cm", "min": 20.0, "max": 100.0,
                       "default": 47.6761, "label": "Back Width"},
        "shoulder_w": {"type": "float", "unit": "cm", "min": 10.0, "max": 80.0,
                       "default": 36.4568, "label": "Shoulder Width"},
        "waist": {"type": "float", "unit": "cm", "min": 40.0, "max": 200.0,
                  "default": 84.3338, "label": "Waist"},
        "waist_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 120.0,
                             "default": 39.1358, "label": "Back Waist Width"},
        "bust_points": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                        "default": 16.9463, "label": "Bust Points"},
        "bum_points": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                       "default": 18.2342, "label": "Bum Points"},
        "waist_line": {"type": "float", "unit": "cm", "min": 10.0, "max": 80.0,
                       "default": 36.8913, "label": "Waist Line"},
        "waist_over_bust_line": {"type": "float", "unit": "cm", "min": 10.0, "max": 90.0,
                                 "default": 40.5603, "label": "Waist Over Bust Line"},
        "shoulder_incl": {"type": "float", "unit": "deg", "min": 0.0, "max": 60.0,
                          "default": 21.6777, "label": "Shoulder Inclination"},
        "bust_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                      "default": 25.6947, "label": "Bust Line"},
        "vert_bust_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                           "default": 21.1388, "label": "Vertical Bust Line"},
        "neck_w": {"type": "float", "unit": "cm", "min": 5.0, "max": 40.0,
                   "default": 18.9328, "label": "Neck Width"},
        "front_armhole_width": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                                "default": 24.6209, "label": "Front Armhole Width"},
        "back_armhole_width": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                               "default": 23.838, "label": "Back Armhole Width"},
        "connecting_width": {"type": "float", "unit": "cm", "min": 2.0, "max": 60.0,
                             "default": 18.4415, "label": "Connecting Width"},
        "sleeveless": {"type": "bool", "default": False, "label": "Sleeveless"},
        "armhole_shape": {"type": "text", "default": "ArmholeCurve",
                          "label": "Armhole Shape"},
        "sleeve_angle": {"type": "float", "unit": "deg", "min": 0.0, "max": 80.0,
                         "default": 10.0, "label": "Sleeve Angle"},
        "sleeve_length": {"type": "float", "unit": "x", "min": 0.1, "max": 1.15,
                          "default": 0.3, "label": "Sleeve Length"},
        "end_width": {"type": "float", "unit": "x", "min": 0.2, "max": 2.0,
                      "default": 1.0, "label": "Sleeve End Width"},
        "opening_dir_mix": {"type": "float", "unit": "fraction", "min": -0.9, "max": 0.8,
                            "default": 0.1, "label": "Opening Direction Mix"},
        "standing_shoulder": {"type": "bool", "default": False,
                              "label": "Standing Shoulder"},
        "standing_shoulder_len": {"type": "float", "unit": "cm", "min": 4.0, "max": 10.0,
                                  "default": 5.0, "label": "Standing Shoulder Length"},
        "smoothing_coeff": {"type": "float", "unit": "fraction", "min": 0.1, "max": 0.4,
                            "default": 0.25, "label": "Armhole Smoothing"},
        "arm_length": {"type": "float", "unit": "cm", "min": 20.0, "max": 120.0,
                       "default": 53.9697, "label": "Arm Length"},
        "wrist": {"type": "float", "unit": "cm", "min": 5.0, "max": 40.0,
                  "default": 16.5945, "label": "Wrist"},
        "collar_kind": {"type": "text", "default": "CircleNeckHalf",
                        "label": "Neckline Shape"},
        "collar_width": {"type": "float", "unit": "fraction", "min": -0.5, "max": 1.0,
                         "default": 0.2, "label": "Collar Width"},
        "front_neck_depth": {"type": "float", "unit": "x", "min": 0.02, "max": 0.6,
                             "default": 0.4, "label": "Front Neck Depth"},
        "back_neck_depth": {"type": "float", "unit": "x", "min": 0.0, "max": 0.6,
                            "default": 0.0, "label": "Back Neck Depth"},
        "neckline_angle": {"type": "float", "unit": "deg", "min": 10.0, "max": 350.0,
                           "default": 90.0, "label": "Neckline Arc Angle"},
        "flip_curve": {"type": "bool", "default": False, "label": "Flip Curve"},
        "collar_style": {"type": "text", "default": "NoPanelsCollar",
                         "label": "Collar Style"},
        "collar_depth": {"type": "float", "unit": "cm", "min": 2.0, "max": 40.0,
                         "default": 12.0, "label": "Collar Depth"},
        "lapel_standing": {"type": "bool", "default": False, "label": "Standing Lapel"},
        "head_l": {"type": "float", "unit": "cm", "min": 10.0, "max": 40.0,
                   "default": 26.3262, "label": "Head Length"},
        "hood_length": {"type": "float", "unit": "x", "min": 0.5, "max": 1.5,
                        "default": 1.0, "label": "Hood Length"},
        "hood_depth": {"type": "float", "unit": "x", "min": 0.5, "max": 2.0,
                       "default": 1.0, "label": "Hood Depth"},
    },
}


def _sleeveless_projection(incline, width, angle, smoothing, kind):
    start = (incline, width)
    end = (0.0, 0.0)
    if kind == "ArmholeSquare":
        return [line_segment(end, (incline, 0.0)), line_segment((incline, 0.0), start)]
    if kind == "ArmholeAngle":
        middle = (incline * (1.0 - smoothing), smoothing * width)
        return [line_segment(end, middle), line_segment(middle, start)]
    control_1 = rel_to_abs_2d(start, end, (0.5, 0.2))
    control_2 = rel_to_abs_2d(start, end, (0.8, 0.35))
    return [Segment(end, start, Bezier(controls=(control_2, control_1)))]


def compose_shirt(front, back, front_armhole_width, back_armhole_width,
                  collar_width, front_depth, back_depth, params: dict,
                  front_name: str = "bodice_front_half",
                  back_name: str = "bodice_back_half"):
    """Cut the sleeve/collar openings in and assemble the right-half panels."""
    shoulder_w = float(params["shoulder_w"])
    shoulder_inclination = float(params["shoulder_incl"])
    sleeve_balance = (shoulder_w - 2.0) / 2.0

    front_neck = neckline_half(str(params["collar_kind"]), front_depth, collar_width,
                               angle=float(params["neckline_angle"]),
                               flip=bool(params["flip_curve"]))
    back_neck = neckline_half("Circle", back_depth, collar_width)

    rest_angle = max(math.radians(float(params["sleeve_angle"])),
                     math.radians(shoulder_inclination))
    connecting_width = float(params["connecting_width"])
    front_incline = front_armhole_width - sleeve_balance
    back_incline = back_armhole_width - sleeve_balance
    sleeveless = bool(params["sleeveless"])
    if sleeveless:
        front_projection = _sleeveless_projection(
            front_incline, connecting_width, rest_angle,
            float(params["smoothing_coeff"]), str(params["armhole_shape"]))
        back_projection = _sleeveless_projection(
            back_incline, connecting_width, rest_angle,
            float(params["smoothing_coeff"]), str(params["armhole_shape"]))
        front_opening = back_opening = None
    else:
        front_projection, front_opening = armhole_shapes(
            front_incline, connecting_width, rest_angle,
            float(params["opening_dir_mix"]))
        back_projection, back_opening = armhole_shapes(
            back_incline, connecting_width, rest_angle,
            float(params["opening_dir_mix"]))
        front_projection = [front_projection]
        back_projection = [back_projection]

    front = cut_corner_segments(front, len(front) - 3, front_projection)
    front = cut_corner_segments(front, len(front) - 2, front_neck)
    back = cut_corner_segments(back, len(back) - 3, back_projection)
    back = cut_corner_segments(back, len(back) - 2, back_neck)

    panels = [
        segments_to_gcd_panel(front_name, front, scale=CM_TO_MM),
        segments_to_gcd_panel(back_name, back, scale=CM_TO_MM),
    ]
    if not sleeveless:
        sleeve_params = dict(params)
        panels.append(_sleeve_panel("sleeve_front", front_opening, sleeve_params))
        panels.append(_sleeve_panel("sleeve_back", back_opening, sleeve_params))

    style = str(params["collar_style"]).strip()
    front_length = chain_length(front_neck)
    back_length = chain_length(back_neck)
    if style == "Turtle":
        depth = float(params["collar_depth"])
        panels.append(straight_band("collar_front", front_length, depth))
        panels.append(straight_band("collar_back", back_length, depth))
    elif style == "SimpleLapel":
        depth = float(params["collar_depth"])
        panels.append(lapel_spec("collar_front", front_length, depth))
        if bool(params["lapel_standing"]):
            panels.append(straight_band("collar_back", back_length, depth))
        else:
            parameters = arc_parameters(back_neck)
            if parameters is not None:
                panels.append(circle_arc_spec("collar_back", parameters[0], depth,
                                              parameters[1]))
    elif style == "Hood":
        hood_depth = collar_width / 2.0 * float(params["hood_depth"])
        hood = hood_spec("hood", front_depth, back_depth, front_length, back_length,
                         collar_width, float(params["head_l"]) * float(params["hood_length"]),
                         hood_depth)
        panels.append(segments_to_gcd_panel("hood", hood, scale=CM_TO_MM))
    return panels


def build(params: dict):
    bodice_params = {key: params[key] for key in _BODICE_KEYS}
    front = front_segments(bodice_params)
    back = back_segments(bodice_params)

    shoulder_w = float(params["shoulder_w"])
    shoulder_inclination = float(params["shoulder_incl"])
    base_sleeve_balance = shoulder_w - 2.0
    minimum_collar = float(params["neck_w"])
    maximum_collar = base_sleeve_balance - 2.0
    collar_width_fraction = float(params["collar_width"])
    collar_width = lerp(minimum_collar, maximum_collar, collar_width_fraction) \
        if collar_width_fraction >= 0.0 \
        else lerp(0.0, minimum_collar, 1.0 + collar_width_fraction)

    shoulder_tan = math.tan(math.radians(shoulder_inclination))
    body_bust_line = (2.0 / 3.0) * float(params["vert_bust_line"]) \
        + (1.0 / 3.0) * float(params["bust_line"])
    # The front half's width at the neck is shoulder_w/2; the back half uses
    # BodiceBackHalf.get_width(), which returns back_width/2.
    front_adjustment = shoulder_tan * (shoulder_w / 2.0 - collar_width / 2.0)
    back_adjustment = shoulder_tan * (float(params["back_width"]) / 2.0 - collar_width / 2.0)
    front_max = segment_length(front[-1]) - shoulder_tan * (shoulder_w / 2.0) - 1.0
    back_max = segment_length(back[-1]) - shoulder_tan * (float(params["back_width"]) / 2.0) - 1.0
    front_depth = min(float(params["front_neck_depth"]) * body_bust_line, front_max) \
        + front_adjustment
    back_depth = min(float(params["back_neck_depth"]) * body_bust_line, back_max) \
        + back_adjustment

    return compose_shirt(front, back, float(params["front_armhole_width"]),
                         float(params["back_armhole_width"]), collar_width,
                         front_depth, back_depth, params)
