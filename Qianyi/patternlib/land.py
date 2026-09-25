"""Landing a pattern specification onto the edge forms the editor stores."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .curves import Vec2, as_vec2
from .spec import PatternSpec, edge_points


@dataclass
class LandedEdge:
    """One edge exactly as the editor will hold it."""

    v0: int
    v1: int
    kind: str                     # "straight" or "bezier"
    points: tuple[Vec2, ...]      # straight: (p0, p1); bezier: (p0, c1, c2, p1)
    name: str = ""
    sewable: bool = True


@dataclass
class LandedPattern:
    """A pattern in editor form: vertices plus the edges between them."""

    name: str
    vertices: list[Vec2] = field(default_factory=list)
    edges: list[LandedEdge] = field(default_factory=list)


def land_pattern(pattern: PatternSpec) -> LandedPattern:
    """Turn a component's pattern into vertices and edges the editor can store.

    A curve the editor can hold as a single edge stays one edge. A point list
    (a ragged or decorative run) becomes several straight edges with the
    intermediate vertices added in between; the first segment keeps the edge's
    label and the following ones get a ``#k`` suffix, so the label still says
    where the run starts.
    """
    vertices = [as_vec2(v) for v in pattern.vertices]
    edges: list[LandedEdge] = []

    # Deliberate Python loop: each edge may become a different number of editor
    # edges, and every one of them is a separate object, so this cannot be a
    # single numpy operation.
    for index, edge in enumerate(pattern.edges):
        p0, p1 = edge_points(pattern, index)
        frontend_edges = edge.curve.to_frontend(p0, p1)
        if not frontend_edges:
            raise ValueError(f"edge '{edge.name}' produced no editor edge")
        start = edge.v0
        last = len(frontend_edges) - 1
        for k, frontend_edge in enumerate(frontend_edges):
            if k == last:
                target = edge.v1
            else:
                target = len(vertices)
                vertices.append(as_vec2(frontend_edge.points[-1]))
            edges.append(LandedEdge(
                v0=start,
                v1=target,
                kind=frontend_edge.kind,
                points=frontend_edge.points,
                name=edge.name if k == 0 else f"{edge.name}#{k}",
                sewable=edge.sewable,
            ))
            start = target

    return LandedPattern(name=pattern.name, vertices=vertices, edges=edges)


def topology_of(landed: LandedPattern) -> tuple:
    """Structure only: what has to match for an in-place rewrite."""
    return (
        len(landed.vertices),
        tuple((edge.v0, edge.v1, edge.kind) for edge in landed.edges),
    )


def landed_boundary(landed: LandedPattern, per_edge: int = 24) -> np.ndarray:
    """The closed outline of a landed pattern as one (N, 2) float32 array.

    Every edge contributes its sampled points except the last, which the next
    edge starts with, so the concatenation is exactly the loop the
    self-intersection test expects. Used to check a pattern *before* it is
    written into the editor, so an invalid parameter never reaches the mesh.
    """
    chunks = []
    # Deliberate Python loop: edges are Python objects with their own point
    # counts, so the concatenation cannot be expressed as one numpy call.
    for edge in landed.edges:
        points = np.asarray(edge.points, dtype=np.float64)
        if edge.kind == "bezier":
            array = _sample_cubic(points, per_edge)
        else:
            array = _sample_line(points, per_edge)
        chunks.append(array[:-1])
    if not chunks:
        return np.empty((0, 2), dtype=np.float32)
    return np.concatenate(chunks, dtype=np.float32)


def _sample_cubic(points: np.ndarray, count: int) -> np.ndarray:
    """Sampled cubic Bezier, vectorised over the parameter column."""
    t = np.linspace(0.0, 1.0, max(int(count), 2))[:, None]
    s = 1.0 - t
    weights = np.concatenate((s ** 3, 3.0 * s * s * t, 3.0 * s * t * t, t ** 3), axis=1)
    return weights @ np.asarray(points, dtype=np.float64)


def _sample_line(points: np.ndarray, count: int) -> np.ndarray:
    """Sampled straight edge, vectorised over the parameter column."""
    t = np.linspace(0.0, 1.0, max(int(count), 2))[:, None]
    start = points[0]
    return start[None, :] + t * (points[-1] - start)[None, :]
