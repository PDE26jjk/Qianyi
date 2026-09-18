"""Panel and edge specification produced by a component.

A component returns panels; a panel is a closed, counter-clockwise loop of
edges over its vertex list. Everything the rest of the add-on needs to create
a panel is here, and nothing about Blender is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .curves import Curve, Line, Vec2, as_vec2, signed_area

AUTO_LABEL_PATTERN = re.compile(r"^edge\d+$")


class PanelSpecError(ValueError):
    """Raised when a component returns a panel that cannot be built."""


@dataclass(frozen=True)
class EdgeSpec:
    """One edge of a panel loop.

    ``name`` is an optional seam label. An empty name means "positional": the
    panel finalisation step replaces it with ``edge<i>``, derived from the edge
    order in the loop. A label is a hint, never a contract.
    """

    v0: int
    v1: int
    curve: Curve = field(default_factory=Line)
    name: str = ""
    sewable: bool = True


@dataclass
class PanelSpec:
    """A panel as the component describes it, before finalisation."""

    name: str
    vertices: list[Vec2]
    edges: list[EdgeSpec]


@dataclass
class ComponentSpec:
    """Everything one component produced for one parameter block."""

    component_id: str
    params: dict
    panels: list[PanelSpec] = field(default_factory=list)
    seams: list["SeamSpec"] = field(default_factory=list)


@dataclass(frozen=True)
class SeamSpec:
    """One internal seam the generator creates once, at first generation.

    Each side is a panel slot plus the label of one edge in that panel. The
    labels are the semantic edge names the component gives its boundary; they
    are also what the rebuild remap uses to keep a seam attached when the
    edge order changes.
    """

    panel_a: str
    edge_a: str
    panel_b: str
    edge_b: str
    reverse: bool = False


def auto_label(index: int) -> str:
    """Positional label of the edge at ``index`` in the loop."""
    return f"edge{index}"


def finalize_panel(panel: PanelSpec) -> PanelSpec:
    """Validate a panel and give every unnamed edge its positional label.

    The returned panel is a copy; the input is left alone so a component can
    reuse the specification objects it built.
    """
    if not panel.name:
        raise PanelSpecError("panel has no name")
    # A degenerate panel (one point, one edge, zero area) is a legal state while
    # a panel is being edited - the engine reports it as an intersection and the
    # mesh stage refuses to build it - so the rule here is "at least one vertex
    # and one edge" instead of demanding a real area.
    if len(panel.vertices) < 1:
        raise PanelSpecError(f"panel '{panel.name}' has no vertices")
    if len(panel.edges) < 1:
        raise PanelSpecError(f"panel '{panel.name}' has no edges")

    vertices = [as_vec2(v) for v in panel.vertices]
    edges = list(panel.edges)

    # Loop consistency is pure index arithmetic, so it runs as one numpy pass:
    # every edge must end where the next one starts, wrapping around the loop.
    starts = np.fromiter((edge.v0 for edge in edges), dtype=np.int64, count=len(edges))
    ends = np.fromiter((edge.v1 for edge in edges), dtype=np.int64, count=len(edges))
    if starts.min() < 0 or ends.min() < 0 or starts.max() >= len(vertices) or ends.max() >= len(vertices):
        raise PanelSpecError(f"panel '{panel.name}' references a missing vertex")
    broken = np.flatnonzero(ends != np.roll(starts, -1))
    if broken.size:
        index = int(broken[0])
        raise PanelSpecError(
            f"panel '{panel.name}' is not a closed loop: edge {index} ends at vertex "
            f"{ends[index]} but edge {(index + 1) % len(edges)} starts at vertex "
            f"{starts[(index + 1) % len(edges)]}")

    labels: list[str] = []
    explicit: set[str] = set()
    for i, edge in enumerate(edges):
        if not edge.name:
            continue
        if edge.name in explicit:
            raise PanelSpecError(f"panel '{panel.name}' labels two edges '{edge.name}'")
        if AUTO_LABEL_PATTERN.match(edge.name):
            raise PanelSpecError(
                f"panel '{panel.name}' uses the reserved positional label '{edge.name}'")
        explicit.add(edge.name)

    for i, edge in enumerate(edges):
        labels.append(edge.name if edge.name else auto_label(i))

    if len(set(labels)) != len(labels):
        raise PanelSpecError(f"panel '{panel.name}' has duplicate edge labels")

    # A clearly clockwise loop is a component bug; a zero-area outline is a
    # degenerate panel and is left to the outline test downstream.
    if signed_area(vertices) < -1e-9:
        raise PanelSpecError(f"panel '{panel.name}' is not counter-clockwise")

    finalized_edges = [
        EdgeSpec(v0=edge.v0, v1=edge.v1, curve=edge.curve, name=label, sewable=edge.sewable)
        for edge, label in zip(edges, labels)
    ]
    return PanelSpec(name=panel.name, vertices=vertices, edges=finalized_edges)


def edge_points(panel: PanelSpec, index: int) -> tuple[Vec2, Vec2]:
    """The two endpoints the edge at ``index`` spans."""
    edge = panel.edges[index]
    return panel.vertices[edge.v0], panel.vertices[edge.v1]


def panel_boundary_sample(panel: PanelSpec, per_edge: int = 32) -> np.ndarray:
    """Sampled boundary of the whole loop, used for matching after a rebuild."""
    samples = []
    for index, edge in enumerate(panel.edges):
        p0, p1 = edge_points(panel, index)
        points = edge.curve.sample(p0, p1, per_edge)
        samples.append(points[:-1] if index < len(panel.edges) - 1 else points)
    return np.concatenate(samples, axis=0) if samples else np.empty((0, 2))


def label_index(panel: PanelSpec, label: str) -> int:
    """Index of the first edge carrying ``label``, or -1."""
    for index, edge in enumerate(panel.edges):
        if edge.name == label:
            return index
    return -1


def reference_point(panel: PanelSpec) -> Vec2:
    """The panel's reference point: its first vertex.

    Components are expected to keep this point roughly where it was when only
    shape parameters change, so the mesh resample keeps matching the previous
    mesh. See :func:`reference_shift`.
    """
    return as_vec2(panel.vertices[0])


def reference_shift(old: PanelSpec, new: PanelSpec) -> float:
    """How far a panel's reference point moved between two generations (mm)."""
    a = np.asarray(reference_point(old), dtype=float)
    b = np.asarray(reference_point(new), dtype=float)
    return float(np.hypot(*(b - a)))
