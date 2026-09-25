"""Shared helpers for the GarmentCode-derived presets.

The presets keep GarmentCode's native units on input (centimetres) so their
parameters can be copied from a GarmentCode body/design file unchanged, and
scale the generated panel coordinates to the add-on's millimetres.
"""

from __future__ import annotations

from ...curves import Line
from ...spec import EdgeSpec, PatternSpec

CM_TO_MM = 10.0


def mm(value_cm: float) -> float:
    """GarmentCode centimetres to the add-on's millimetres."""
    return float(value_cm) * CM_TO_MM


def lerp(a: float, b: float, t: float) -> float:
    """GarmentCode's ``lin_interpolation``."""
    return (1.0 - t) * a + t * b


def lerp_point(a, b, t: float):
    """Linear interpolation between two 2D points."""
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def polygon_cm(name: str, vertices_cm) -> PatternSpec:
    """A closed counter-clockwise loop of straight edges.

    GarmentCode panels are clockwise, so every preset below reverses the
    source loop to satisfy this library's CCW rule (see ``finalize_pattern``).
    Edge labels stay positional (``edge0``...): the presets do not publish
    sewing semantics.
    """
    # Deliberate comprehensions: the point scaling and the edge construction
    # each build a list of Python objects, which numpy cannot do.
    scaled = [(mm(x), mm(y)) for x, y in vertices_cm]
    edges = [EdgeSpec(i, (i + 1) % len(scaled), Line()) for i in range(len(scaled))]
    return PatternSpec(name=name, vertices=scaled, edges=edges)


def name_side_edges(panel: PatternSpec, left_name: str = "left",
                    right_name: str = "right") -> PatternSpec:
    """Label the leftmost and rightmost edges of a panel.

    The labels are what the generator's internal-seam declaration refers to,
    and they survive the rebuild remap. Returns the same panel with the two
    edges relabelled in place (``PatternSpec`` is a mutable record).
    """
    vertices = panel.vertices
    # Deliberate comprehension: one midpoint per Python EdgeSpec.
    midpoints = [(vertices[edge.v0][0] + vertices[edge.v1][0]) / 2.0
                 for edge in panel.edges]
    left = min(range(len(midpoints)), key=lambda index: midpoints[index])
    right = max(range(len(midpoints)), key=lambda index: midpoints[index])
    for index, edge_name in ((left, left_name), (right, right_name)):
        edge = panel.edges[index]
        panel.edges[index] = EdgeSpec(edge.v0, edge.v1, edge.curve, edge_name, edge.sewable)
    return panel
