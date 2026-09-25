"""Simple lapel collar preset, transcribed from GarmentCode's ``collars.py``.

Source class: ``SimpleLapel`` (one lapel panel plus a straight or curved back
panel).
"""

from __future__ import annotations

from ._collar import arc_parameters, chain_length, neckline_half
from ._gcd_panels import circle_arc_spec
from ._common import polygon_cm
from .simple_lapel import lapel_spec

COMPONENT_ID = "gc_simple_lapel_collar"
VERSION = 1
LABEL = "GC Simple Lapel Collar"
CATEGORY = "GarmentCode"
DESCRIPTION = "GarmentCode SimpleLapel: one lapel panel and a back collar panel."

SCHEMA = {
    "id": COMPONENT_ID,
    "version": VERSION,
    "params": {
        "width": {"type": "float", "unit": "cm", "min": 5.0, "max": 60.0,
                  "default": 18.0, "label": "Collar Width"},
        "depth": {"type": "float", "unit": "cm", "min": 2.0, "max": 40.0,
                  "default": 12.0, "label": "Collar Depth"},
        "front_neck_depth": {"type": "float", "unit": "cm", "min": 1.0, "max": 30.0,
                             "default": 8.0, "label": "Front Neck Depth"},
        "back_neck_depth": {"type": "float", "unit": "cm", "min": 1.0, "max": 30.0,
                            "default": 5.0, "label": "Back Neck Depth"},
        "neckline": {"type": "text", "default": "CircleArc",
                     "label": "Neckline Shape"},
        "neckline_angle": {"type": "float", "unit": "deg", "min": 10.0, "max": 350.0,
                           "default": 90.0, "label": "Neckline Arc Angle"},
        "flip_curve": {"type": "bool", "default": False, "label": "Flip Curve"},
        "standing": {"type": "bool", "default": False, "label": "Standing Lapel"},
    },
}


def _band(name, width, depth):
    return polygon_cm(name, [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)])


def build(params: dict):
    width = float(params["width"])
    depth = float(params["depth"])
    front = neckline_half(
        str(params["neckline"]), float(params["front_neck_depth"]), width,
        angle=float(params["neckline_angle"]), flip=bool(params["flip_curve"]))
    back = neckline_half("Circle", float(params["back_neck_depth"]), width)
    back_panel = _band("collar_back", chain_length(back), depth)
    if not bool(params["standing"]):
        parameters = arc_parameters(back)
        if parameters is not None:
            radius, angle = parameters
            back_panel = circle_arc_spec("collar_back", radius, depth, angle)
    return [lapel_spec("collar_front", chain_length(front), depth), back_panel]
