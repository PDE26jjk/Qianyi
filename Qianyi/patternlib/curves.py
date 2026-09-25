"""Curve primitives for parametric patterns.

A curve owns shape, not endpoints: the pattern's vertex list owns the two end
points and every primitive is evaluated between them. That keeps a pattern's
topology (which vertices an edge connects) separate from its geometry, so a
shape change never renumbers the pattern.

Every primitive reduces to one of the two edge forms the editor already stores,
or to a sequence of straight edges:

* ``FrontendEdge("straight", (p0, p1))``      - a two-point edge, vector handles
* ``FrontendEdge("bezier", (p0, c1, c2, p1))`` - a two-point edge, free handles
* a point list becomes several straight edges
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

Vec2 = tuple[float, float]

_EPS = 1e-9


def as_vec2(point: Sequence[float]) -> Vec2:
    return (float(point[0]), float(point[1]))


def parameter_line(count: int) -> np.ndarray:
    """``(count, 1)`` column of parameters; every sampler works on columns."""
    return np.linspace(0.0, 1.0, max(int(count), 2))[:, None]


def left_normal(p0: Vec2, p1: Vec2) -> np.ndarray:
    """Unit normal pointing to the left of the direction ``p0 -> p1``."""
    delta = np.asarray(p1, dtype=float) - np.asarray(p0, dtype=float)
    length = float(np.hypot(delta[0], delta[1]))
    if length <= _EPS:
        return np.array((0.0, 0.0))
    return np.array((-delta[1] / length, delta[0] / length))


@dataclass(frozen=True)
class FrontendEdge:
    """One edge in the form the editor stores it."""

    kind: str
    points: tuple[Vec2, ...]


class Curve:
    """Common interface of the curve primitives."""

    def point(self, p0: Vec2, p1: Vec2, t: float) -> Vec2:
        raise NotImplementedError

    def sample(self, p0: Vec2, p1: Vec2, count: int = 64) -> np.ndarray:
        """Return ``count`` points along the curve, endpoints included."""
        raise NotImplementedError

    def length(self, p0: Vec2, p1: Vec2, count: int = 256) -> float:
        points = self.sample(p0, p1, count)
        return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))

    def to_frontend(self, p0: Vec2, p1: Vec2) -> list[FrontendEdge]:
        raise NotImplementedError


@dataclass(frozen=True)
class Line(Curve):
    """Straight edge between the pattern vertices."""

    def point(self, p0: Vec2, p1: Vec2, t: float) -> Vec2:
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)

    def sample(self, p0: Vec2, p1: Vec2, count: int = 64) -> np.ndarray:
        t = parameter_line(count)
        start = np.asarray(p0, dtype=float)
        return start[None, :] + t * (np.asarray(p1, dtype=float) - start)[None, :]

    def to_frontend(self, p0: Vec2, p1: Vec2) -> list[FrontendEdge]:
        return [FrontendEdge("straight", (as_vec2(p0), as_vec2(p1)))]


@dataclass(frozen=True)
class Bezier(Curve):
    """Quadratic (one control point) or cubic (two) Bezier curve.

    Control points are absolute pattern coordinates. A quadratic curve is raised
    to a cubic one, which is exact.
    """

    controls: tuple[Vec2, ...]

    def cubic_controls(self, p0: Vec2, p1: Vec2) -> tuple[Vec2, Vec2]:
        if len(self.controls) == 1:
            q = as_vec2(self.controls[0])
            c1 = (p0[0] + 2.0 / 3.0 * (q[0] - p0[0]), p0[1] + 2.0 / 3.0 * (q[1] - p0[1]))
            c2 = (p1[0] + 2.0 / 3.0 * (q[0] - p1[0]), p1[1] + 2.0 / 3.0 * (q[1] - p1[1]))
            return c1, c2
        if len(self.controls) == 2:
            return as_vec2(self.controls[0]), as_vec2(self.controls[1])
        raise ValueError(f"a Bezier edge needs one or two control points, got {len(self.controls)}")

    def point(self, p0: Vec2, p1: Vec2, t: float) -> Vec2:
        c1, c2 = self.cubic_controls(p0, p1)
        s = 1.0 - t
        b0, b1, b2, b3 = s * s * s, 3.0 * s * s * t, 3.0 * s * t * t, t * t * t
        return (
            b0 * p0[0] + b1 * c1[0] + b2 * c2[0] + b3 * p1[0],
            b0 * p0[1] + b1 * c1[1] + b2 * c2[1] + b3 * p1[1],
        )

    def sample(self, p0: Vec2, p1: Vec2, count: int = 64) -> np.ndarray:
        t = parameter_line(count)
        s = 1.0 - t
        c1, c2 = self.cubic_controls(p0, p1)
        controls = np.asarray((p0, c1, c2, p1), dtype=float)
        weights = np.concatenate((s ** 3, 3.0 * s * s * t, 3.0 * s * t * t, t ** 3), axis=1)
        return weights @ controls

    def to_frontend(self, p0: Vec2, p1: Vec2) -> list[FrontendEdge]:
        c1, c2 = self.cubic_controls(p0, p1)
        return [FrontendEdge("bezier", (as_vec2(p0), c1, c2, as_vec2(p1)))]


@dataclass(frozen=True)
class Arc(Curve):
    """Circular arc between the two pattern vertices.

    ``bulge`` is the signed sagitta as a fraction of the chord length
    (the AutoCAD bulge, ``tan(sweep / 4)``). A positive bulge bends the arc to
    the left of the direction ``p0 -> p1``; zero is a straight edge.
    """

    bulge: float = 0.0

    def geometry(self, p0: Vec2, p1: Vec2):
        """Return ``(center, radius, start_angle, sweep)`` or None for a line."""
        p0v = np.asarray(p0, dtype=float)
        p1v = np.asarray(p1, dtype=float)
        delta = p1v - p0v
        chord = float(np.hypot(delta[0], delta[1]))
        if chord <= _EPS or abs(self.bulge) <= _EPS:
            return None
        sagitta = self.bulge * chord / 2.0
        radius = (chord * chord / 4.0 + sagitta * sagitta) / (2.0 * abs(sagitta))
        mid = (p0v + p1v) / 2.0
        # The centre sits on the opposite side of the chord from the bulge.
        normal = left_normal(as_vec2(p0), as_vec2(p1))
        center = mid - normal * math.copysign(radius - abs(sagitta), sagitta)
        start_angle = math.atan2(p0v[1] - center[1], p0v[0] - center[0])
        half_angle = math.asin(min(1.0, (chord / 2.0) / radius))
        sweep = -math.copysign(2.0 * half_angle, sagitta)
        return center, radius, start_angle, sweep

    def point(self, p0: Vec2, p1: Vec2, t: float) -> Vec2:
        geometry = self.geometry(p0, p1)
        if geometry is None:
            return Line().point(p0, p1, t)
        center, radius, start_angle, sweep = geometry
        angle = start_angle + sweep * t
        return (float(center[0] + radius * math.cos(angle)),
                float(center[1] + radius * math.sin(angle)))

    def sample(self, p0: Vec2, p1: Vec2, count: int = 64) -> np.ndarray:
        geometry = self.geometry(p0, p1)
        if geometry is None:
            return Line().sample(p0, p1, count)
        center, radius, start_angle, sweep = geometry
        angle = start_angle + sweep * parameter_line(count)
        x = center[0] + radius * np.cos(angle)
        y = center[1] + radius * np.sin(angle)
        return np.concatenate((x, y), axis=1)

    def to_frontend(self, p0: Vec2, p1: Vec2) -> list[FrontendEdge]:
        geometry = self.geometry(p0, p1)
        if geometry is None:
            return Line().to_frontend(p0, p1)
        center, radius, start_angle, sweep = geometry
        segments = max(1, int(math.ceil(abs(sweep) / (math.pi / 2.0))))
        step = sweep / segments
        # Standard circular-arc-to-cubic-Bezier control-point factor.
        handle = 4.0 / 3.0 * math.tan(step / 4.0)
        # Deliberate Python loop: an arc splits into at most four edges, each of
        # which is emitted as its own object, so there is nothing to vectorise.
        edges = []
        for i in range(segments):
            a0 = start_angle + step * i
            a1 = a0 + step
            q0 = (center[0] + radius * math.cos(a0), center[1] + radius * math.sin(a0))
            q1 = (center[0] + radius * math.cos(a1), center[1] + radius * math.sin(a1))
            tangent0 = (-math.sin(a0), math.cos(a0))
            tangent1 = (-math.sin(a1), math.cos(a1))
            c1 = (q0[0] + handle * radius * tangent0[0], q0[1] + handle * radius * tangent0[1])
            c2 = (q1[0] - handle * radius * tangent1[0], q1[1] - handle * radius * tangent1[1])
            edges.append(FrontendEdge("bezier", (q0, c1, c2, q1)))
        return edges


@dataclass(frozen=True)
class Polyline(Curve):
    """Explicit point list, used by decorative and ragged runs.

    The first and last points must coincide with the pattern vertices the edge
    connects, so a noisy run joins its neighbours without a step.
    """

    points: tuple[Vec2, ...]

    def _checked(self, p0: Vec2, p1: Vec2) -> tuple[Vec2, ...]:
        points = np.asarray(self.points, dtype=float)
        if points.ndim != 2 or points.shape[0] < 2:
            raise ValueError("a polyline edge needs at least two points")
        if np.hypot(*(points[0] - np.asarray(p0, dtype=float))) > 1e-6:
            raise ValueError("polyline does not start at the edge's first vertex")
        if np.hypot(*(points[-1] - np.asarray(p1, dtype=float))) > 1e-6:
            raise ValueError("polyline does not end at the edge's second vertex")
        return points

    def point(self, p0: Vec2, p1: Vec2, t: float) -> Vec2:
        points = self._checked(p0, p1)
        lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
        cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
        total = cumulative[-1]
        if total <= _EPS:
            return as_vec2(points[0])
        target = t * total
        index = int(np.searchsorted(cumulative, target, side="right") - 1)
        index = min(max(index, 0), len(lengths) - 1)
        span = lengths[index]
        local = 0.0 if span <= _EPS else (target - cumulative[index]) / span
        return (float(points[index][0] + (points[index + 1][0] - points[index][0]) * local),
                float(points[index][1] + (points[index + 1][1] - points[index][1]) * local))

    def sample(self, p0: Vec2, p1: Vec2, count: int = 64) -> np.ndarray:
        return self._checked(p0, p1)

    def to_frontend(self, p0: Vec2, p1: Vec2) -> list[FrontendEdge]:
        points = self._checked(p0, p1)
        # One edge object per segment: the result is a list of objects, so a
        # comprehension is the clearest form (numpy cannot build Python objects).
        return [FrontendEdge("straight", (tuple(points[i]), tuple(points[i + 1])))
                for i in range(len(points) - 1)]


def signed_area(points: Sequence[Vec2]) -> float:
    """Shoelace area of a closed loop; positive when counter-clockwise."""
    array = np.asarray(points, dtype=float)
    x, y = array[:, 0], array[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
