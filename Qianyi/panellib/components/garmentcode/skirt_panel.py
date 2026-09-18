"""Panel-skirt piece preset, transcribed from GarmentCode's ``skirt_paneled.py``.

Source class: ``SkirtPanel``. Only the panel geometry is ported; the waist
ruffle is kept as the extra top width it produces, not as a stitching rule.
"""

from __future__ import annotations

from ._common import lerp_point, polygon_cm

COMPONENT_ID = "gc_skirt_panel"
VERSION = 1
LABEL = "GC Skirt Panel"
CATEGORY = "GarmentCode"
DESCRIPTION = ("GarmentCode SkirtPanel: a flared trapezoid with optional cuts "
               "at the bottom corners.")

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "waist_length": {"type": "float", "unit": "cm", "min": 10.0, "max": 200.0,
                         "default": 70.0, "label": "Waist Length"},
        "length": {"type": "float", "unit": "cm", "min": 5.0, "max": 200.0,
                   "default": 70.0, "label": "Length"},
        "ruffles": {"type": "float", "unit": "x", "min": 0.5, "max": 3.0,
                    "default": 1.0, "label": "Waist Ruffles"},
        "flare": {"type": "float", "unit": "cm", "min": 0.0, "max": 100.0,
                  "default": 0.0, "label": "Flare"},
        "bottom_cut": {"type": "float", "unit": "cm", "min": 0.0, "max": 200.0,
                       "default": 0.0, "label": "Bottom Cut"},
    },
}


def skirt_panel_spec(name: str, waist_length: float, length: float,
                     ruffles: float, flare: float, bottom_cut: float):
    """One GarmentCode ``SkirtPanel`` under the requested name."""
    top_width = waist_length * ruffles
    low_width = top_width + 2.0 * flare
    x_shift_top = (low_width - top_width) / 2.0
    cut = 0.0 if length <= 0.0 else max(0.0, min(bottom_cut / length, 1.0))

    # Counter-clockwise version of GarmentCode's clockwise loop:
    # bottom -> left -> waist -> right.
    bottom_left = (0.0, 0.0)
    bottom_right = (low_width, 0.0)
    waist_right = (x_shift_top + top_width, length)
    waist_left = (x_shift_top, length)

    vertices = [bottom_left, bottom_right]
    if cut > 0.0:
        # GarmentCode inserts one vertex on each slanted side at the cut height.
        vertices.append(lerp_point(bottom_right, waist_right, cut))
        vertices.append(waist_right)
        vertices.append(waist_left)
        vertices.append(lerp_point(bottom_left, waist_left, cut))
    else:
        vertices.append(waist_right)
        vertices.append(waist_left)
    return polygon_cm(name, vertices)


def build(params: dict):
    return [skirt_panel_spec(
        "skirt_panel",
        waist_length=float(params["waist_length"]),
        length=float(params["length"]),
        ruffles=float(params["ruffles"]),
        flare=float(params["flare"]),
        bottom_cut=float(params["bottom_cut"]),
    )]
