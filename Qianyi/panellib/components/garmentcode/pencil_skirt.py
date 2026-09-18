"""Pencil skirt preset, transcribed from GarmentCode's ``skirt_paneled.py``.

Source classes: ``PencilSkirt`` and ``FittedSkirtPanel``. The preset produces
the two fitted panels (front and back). Only panel geometry is ported:
interfaces, stitching rules and 3D placement are intentionally left out.
The optional ``style_side_cut`` is not ported (its default is disabled).
"""

from __future__ import annotations

import math

from ._common import CM_TO_MM, lerp
from ._kernel import (curve_from_tangents, insert_notches, line_segment,
                      quad_segment, segments_to_panel, split_segment)

COMPONENT_ID = "gc_pencil_skirt"
VERSION = 1
LABEL = "GC Pencil Skirt"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode PencilSkirt: fitted front and back panels with "
               "waist darts and optional hem/side slits.")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "hips": {"type": "float", "unit": "cm", "min": 50.0, "max": 220.0,
                 "default": 103.478, "label": "Hips"},
        "hip_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 140.0,
                           "default": 54.8237, "label": "Back Hip Width"},
        "waist": {"type": "float", "unit": "cm", "min": 40.0, "max": 200.0,
                  "default": 84.3338, "label": "Waist"},
        "waist_back_width": {"type": "float", "unit": "cm", "min": 10.0, "max": 120.0,
                             "default": 39.1358, "label": "Back Waist Width"},
        "hips_line": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                      "default": 23.4837, "label": "Hip Line"},
        "leg_length": {"type": "float", "unit": "cm", "min": 20.0, "max": 150.0,
                       "default": 85.2888, "label": "Leg Length"},
        "hip_inclination": {"type": "float", "unit": "deg", "min": 0.0, "max": 40.0,
                            "default": 9.86489, "label": "Hip Inclination"},
        "bust_points": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                        "default": 16.9463, "label": "Bust Points"},
        "bum_points": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                       "default": 18.2342, "label": "Bum Points"},
        "rise": {"type": "float", "unit": "fraction", "min": 0.5, "max": 1.0,
                 "default": 1.0, "label": "Rise"},
        "skirt_length": {"type": "float", "unit": "x", "min": 0.2, "max": 1.0,
                         "default": 0.4, "label": "Length"},
        "flare": {"type": "float", "unit": "x", "min": 0.6, "max": 1.5,
                  "default": 1.0, "label": "Flare"},
        "low_angle": {"type": "float", "unit": "deg", "min": -30.0, "max": 30.0,
                      "default": 0.0, "label": "Hem Angle"},
        "front_slit": {"type": "float", "unit": "fraction", "min": 0.0, "max": 0.9,
                       "default": 0.0, "label": "Front Slit"},
        "back_slit": {"type": "float", "unit": "fraction", "min": 0.0, "max": 0.9,
                      "default": 0.0, "label": "Back Slit"},
        "left_slit": {"type": "float", "unit": "fraction", "min": 0.0, "max": 0.9,
                      "default": 0.0, "label": "Left Slit"},
        "right_slit": {"type": "float", "unit": "fraction", "min": 0.0, "max": 0.9,
                       "default": 0.0, "label": "Right Slit"},
    },
}


def _fitted_panel(name, body_hips, hip_inclination, waist, hips, hips_depth, length,
                  hipline_ext, dart_position, dart_frac, double_dart,
                  slit, left_slit, right_slit, flare, low_angle):
    """One GarmentCode ``FittedSkirtPanel`` as a closed segment chain."""
    hip_side_inclination = math.radians(hip_inclination / 2.0)
    low_width = body_hips * (flare - 1.0) / 4.0 + hips
    adjusted_hips_depth = hips_depth * hipline_ext
    dart_depth = max(hips_depth * dart_frac - (hips_depth - adjusted_hips_depth), 0.0)

    waist_difference = hips - waist
    side_shift = math.tan(hip_side_inclination) * adjusted_hips_depth
    if side_shift > waist_difference:
        side_shift = waist_difference
    angle_shift = math.tan(math.radians(low_angle)) * low_width

    # GarmentCode's corner points, in its own (clockwise) order.
    a = (hips - low_width, angle_shift)
    b = (0.0, length)
    c = (side_shift, length + adjusted_hips_depth)
    d = (2.0 * hips - side_shift, length + adjusted_hips_depth)
    e = (2.0 * hips, length)
    f = (hips + low_width, -angle_shift)
    interior = (sum(p[0] for p in (a, b, c, d, e, f)) / 6.0,
                sum(p[1] for p in (a, b, c, d, e, f)) / 6.0)

    straight = abs(flare - 1.0) < 1e-6
    parts = {}
    if straight:
        parts["right_bottom"] = [line_segment(a, b)]
    else:
        control = curve_from_tangents(a, b, tan1=(0.0, 1.0), guess=(0.75, 0.0))
        parts["right_bottom"] = [quad_segment(a, b, control)]
    parts["right_top"] = [quad_segment(
        b, c, curve_from_tangents(b, c, tan0=(0.0, 1.0), guess=(0.5, 0.0)))]
    parts["top"] = [line_segment(c, d)]
    parts["left_top"] = [quad_segment(
        d, e, curve_from_tangents(d, e, tan1=(0.0, -1.0), guess=(0.5, 0.0)))]
    if straight:
        parts["left_bottom"] = [line_segment(e, f)]
    else:
        control = curve_from_tangents(e, f, tan0=(0.0, -1.0), guess=(0.25, 0.0))
        parts["left_bottom"] = [quad_segment(e, f, control)]
    parts["bottom"] = [line_segment(f, a)]

    # GarmentCode passes the intended dart depth as ``dart_shape``'s second
    # positional argument, which is the dart *side length*, not its depth.
    # Replicate that quirk: the perpendicular depth is the triangle height.
    def dart_height(side_len, width):
        return math.sqrt(max(side_len * side_len - (width / 2.0) ** 2, 0.0))

    # Waist darts: two on the front panel, four on the back panel.
    if waist_difference > side_shift:
        dart_width = waist_difference - side_shift
        top_length = math.dist(c, d)
        if double_dart:
            distance = dart_position * 0.5
            offsets = [
                -(dart_position + distance / 2.0 + dart_width / 2.0) - dart_width / 4.0,
                -(dart_position - distance / 2.0) - dart_width / 4.0,
                dart_position - distance / 2.0 + dart_width / 4.0,
                dart_position + distance / 2.0 + dart_width / 2.0 + dart_width / 4.0,
            ]
            widths = [dart_width / 2.0] * 4
            sides = [dart_depth * 0.9, dart_depth, dart_depth, dart_depth * 0.9]
            depths = [dart_height(side, width) for side, width in zip(sides, widths)]
        else:
            offsets = [-(dart_position + dart_width / 2.0),
                       dart_position + dart_width / 2.0]
            widths = [dart_width, dart_width]
            depths = [dart_height(dart_depth, dart_width)] * 2
        # Deliberate comprehension: one (centre, width, depth) record per
        # dart; these are Python records, not a numeric array.
        notches = [(top_length / 2.0 + offset, width, depth)
                   for offset, width, depth in zip(offsets, widths, depths)]
        parts["top"] = insert_notches(parts["top"][0], notches, interior)

    # Centre hem slit: a very thin, deep V notch at the middle of the hem.
    if slit > 0.0:
        bottom_length = math.dist(f, a)
        parts["bottom"] = insert_notches(
            parts["bottom"][0], [(bottom_length / 2.0, 2.0, slit * length)], interior)

    # Side slits only add a vertex on the side edge; they do not change shape.
    if left_slit > 0.0:
        pieces = split_segment(parts["left_bottom"][0], 1.0 - left_slit)
        parts["left_bottom"] = pieces
    if right_slit > 0.0:
        pieces = split_segment(parts["right_bottom"][0], right_slit)
        parts["right_bottom"] = pieces

    order = ("right_bottom", "right_top", "top", "left_top", "left_bottom", "bottom")
    segments = []
    edge_names = {}
    index = 0
    # Deliberate loops: flatten the per-edge lists and label the seam edges.
    for key in order:
        pieces = parts[key]
        for position, segment in enumerate(pieces):
            segments.append(segment)
            if key == "right_bottom" and position == 0:
                edge_names[index] = "right_lower"
            elif key == "right_top":
                edge_names[index] = "right_upper"
            elif key == "left_top":
                edge_names[index] = "left_upper"
            elif key == "left_bottom" and position == len(pieces) - 1:
                edge_names[index] = "left_lower"
            index += 1
    return segments_to_panel(name, segments, scale=CM_TO_MM, edge_names=edge_names)


def seams(params: dict, panels):
    """The two side seams of the pencil skirt (one pair per side piece)."""
    return [
        ("skirt_front", "right_lower", "skirt_back", "right_lower"),
        ("skirt_front", "right_upper", "skirt_back", "right_upper"),
        ("skirt_front", "left_upper", "skirt_back", "left_upper"),
        ("skirt_front", "left_lower", "skirt_back", "left_lower"),
    ]


def build(params: dict):
    hips = float(params["hips"])
    hip_back_width = float(params["hip_back_width"])
    waist = float(params["waist"])
    waist_back_width = float(params["waist_back_width"])
    hips_line = float(params["hips_line"])
    leg_length = float(params["leg_length"])
    hip_inclination = float(params["hip_inclination"])
    bust_points = float(params["bust_points"])
    bum_points = float(params["bum_points"])
    rise = float(params["rise"])
    length = float(params["skirt_length"]) * leg_length
    flare = float(params["flare"])
    low_angle = float(params["low_angle"])

    adjusted_waist = lerp(hips, waist, rise)
    adjusted_hips_depth = rise * hips_line
    adjusted_back_waist = lerp(hip_back_width, waist_back_width, rise)

    front = _fitted_panel(
        "skirt_front", body_hips=hips, hip_inclination=hip_inclination,
        waist=(adjusted_waist - adjusted_back_waist) / 2.0,
        hips=(hips - hip_back_width) / 2.0,
        hips_depth=adjusted_hips_depth, length=length, hipline_ext=1.0,
        dart_position=bust_points / 2.0, dart_frac=0.8, double_dart=False,
        slit=float(params["front_slit"]), left_slit=float(params["left_slit"]),
        right_slit=float(params["right_slit"]), flare=flare, low_angle=low_angle)
    back = _fitted_panel(
        "skirt_back", body_hips=hips, hip_inclination=hip_inclination,
        waist=adjusted_back_waist / 2.0, hips=hip_back_width / 2.0,
        hips_depth=adjusted_hips_depth, length=length, hipline_ext=1.05,
        dart_position=bum_points / 2.0, dart_frac=0.85, double_dart=True,
        slit=float(params["back_slit"]), left_slit=float(params["left_slit"]),
        right_slit=float(params["right_slit"]), flare=flare, low_angle=low_angle)
    return [front, back]
