"""Pure-numpy geometry kernel for the GarmentCode panel presets.

GarmentCode's fit routines use scipy and svgpathtools. Only a small part of
that surface is needed to transcribe panels:

* :class:`NCurve` - point/derivative/arc length/inverse arc length for lines,
  quadratic and cubic Beziers, and circular arcs.
* :func:`curve_from_tangents` - quadratic Bezier control point that matches
  the endpoint tangents. When both tangents are given the control point is the
  intersection of the two tangent lines (closed form). When only one is given
  the problem is under-determined; this implementation keeps the control
  point's distance from the initial guess, which turns an optimizer artefact
  into a deterministic convention.
* :class:`Segment` helpers - build a counter-clockwise ``PanelSpec`` from a
  chain of line/Bezier segments, split a segment at a length fraction, and cut
  V-shaped notches (darts, hem slits) into a straight edge.

This module is the reference; upstream GarmentCode is only used to sanity
check shapes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ...curves import Arc, Bezier, Curve, Line, Vec2, signed_area
from ...spec import EdgeSpec, PanelSpec

_GL_T, _GL_W = np.polynomial.legendre.leggauss(32)


def lerp_point(a, b, t: float):
    """Linear interpolation between two 2D points (also used for vectors)."""
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def rel_to_abs_2d(start, end, rel_point):
    """GarmentCode's edge-local coordinates to panel coordinates."""
    s = np.asarray(start, dtype=float)
    e = np.asarray(end, dtype=float)
    edge = e - s
    edge_perp = np.array([-edge[1], edge[0]])
    return s + rel_point[0] * edge + rel_point[1] * edge_perp


def abs_to_rel_2d(start, end, point, as_vector: bool = False):
    """Panel coordinates to GarmentCode's edge-local coordinates.

    The 2D cross product is written out as a scalar product: ``np.cross``
    deprecated 2-element vectors in numpy 2.0.
    """
    s = np.asarray(start, dtype=float)
    e = np.asarray(end, dtype=float)
    vector = np.asarray(point, dtype=float)
    edge = e - s
    edge_len = float(np.linalg.norm(edge))
    if edge_len <= 1e-12:
        return np.zeros(2)
    point_vector = vector if as_vector else vector - s
    x = float(edge @ point_vector) / (edge_len * edge_len)
    perpendicular = point_vector - x * edge
    y = float(np.linalg.norm(perpendicular)) / edge_len
    y *= math.copysign(1.0, edge[0] * point_vector[1] - edge[1] * point_vector[0])
    return np.array([x, y])


def curve_from_tangents(start, end, tan0=None, tan1=None, guess=None):
    """Absolute control point of a quadratic Bezier matching endpoint tangents.

    ``tan0``/``tan1`` are absolute direction vectors; ``guess`` is the
    edge-local initial control point (the same convention GarmentCode uses).
    """
    guess = np.array([0.5, 0.0]) if guess is None else np.asarray(guess, dtype=float)
    t0 = None if tan0 is None else abs_to_rel_2d(start, end, tan0, as_vector=True)
    t1 = None if tan1 is None else abs_to_rel_2d(start, end, tan1, as_vector=True)
    if t0 is not None:
        t0 = t0 / np.linalg.norm(t0)
    if t1 is not None:
        t1 = t1 / np.linalg.norm(t1)
    p1 = np.array([1.0, 0.0])

    if t0 is not None and t1 is not None:
        # C = a*t0 and C = P1 - b*t1  ->  [t0, t1] @ [a, b] = P1
        matrix = np.column_stack([t0, t1])
        if abs(float(np.linalg.det(matrix))) > 1e-8:
            a, b = np.linalg.solve(matrix, p1)
            if a > 1e-6 and b > 1e-6:
                return rel_to_abs_2d(start, end, a * t0)
        solution, *_ = np.linalg.lstsq(matrix, p1, rcond=None)
        return rel_to_abs_2d(start, end, solution[0] * t0)
    if t0 is not None:
        return rel_to_abs_2d(start, end, float(np.linalg.norm(guess)) * t0)
    if t1 is not None:
        return rel_to_abs_2d(start, end, p1 - float(np.linalg.norm(p1 - guess)) * t1)
    return rel_to_abs_2d(start, end, guess)


class NCurve:
    """Line/quadratic/cubic Bezier/circular arc with arc-length queries."""

    def __init__(self, cps=None, arc=None):
        if cps is not None:
            self.cps = np.asarray(cps, dtype=float)
            self.kind = {2: "line", 3: "quad", 4: "cubic"}[len(self.cps)]
            self.arc = None
        else:
            self.cps = None
            self.kind = "arc"
            self.arc = dict(arc)

    @staticmethod
    def arc_from_flags(start, end, radius, large_arc, sweep):
        """Circular arc from endpoints plus SVG-style radius/flags.

        The centre side follows the SVG convention: ``large_arc == sweep``
        selects the ``+`` side of the chord. (This sign is easy to get
        backwards; it is the one place where the upstream helper and a naive
        port diverge.)
        """
        s = np.asarray(start, dtype=float)
        e = np.asarray(end, dtype=float)
        delta = e - s
        chord = float(np.linalg.norm(delta))
        if chord <= 1e-12:
            raise ValueError("degenerate arc")
        r = max(float(radius), chord / 2.0 + 1e-12)
        mid = (s + e) / 2.0
        height = math.sqrt(max(r * r - (chord / 2.0) ** 2, 0.0))
        perpendicular = np.array([delta[1], -delta[0]]) / chord
        centre = mid + height * perpendicular if large_arc == sweep \
            else mid - height * perpendicular
        theta0 = math.atan2(s[1] - centre[1], s[0] - centre[0])
        theta1 = math.atan2(e[1] - centre[1], e[0] - centre[0])
        span = theta1 - theta0
        if sweep and span < 0:
            span += 2 * math.pi
        elif not sweep and span > 0:
            span -= 2 * math.pi
        return NCurve(arc=dict(centre=centre, radius=r,
                               theta0=theta0, theta1=theta0 + span))

    def point(self, t):
        if self.kind == "arc":
            theta = self.arc["theta0"] + t * (self.arc["theta1"] - self.arc["theta0"])
            return self.arc["centre"] + self.arc["radius"] * np.array(
                [math.cos(theta), math.sin(theta)])
        p = self.cps
        if self.kind == "line":
            return p[0] + t * (p[1] - p[0])
        if self.kind == "quad":
            return (1 - t) ** 2 * p[0] + 2 * t * (1 - t) * p[1] + t ** 2 * p[2]
        return ((1 - t) ** 3 * p[0] + 3 * t * (1 - t) ** 2 * p[1]
                + 3 * t ** 2 * (1 - t) * p[2] + t ** 3 * p[3])

    def derivative(self, t):
        t = np.asarray(t, dtype=float)
        if self.kind == "arc":
            span = self.arc["theta1"] - self.arc["theta0"]
            theta = self.arc["theta0"] + t * span
            return self.arc["radius"] * span * np.stack(
                [-np.sin(theta), np.cos(theta)], axis=-1)
        p = self.cps
        if self.kind == "line":
            return np.broadcast_to(p[1] - p[0], t.shape + (2,)).copy()
        if self.kind == "quad":
            return 2 * ((1 - t)[..., None] * (p[1] - p[0])
                        + t[..., None] * (p[2] - p[1]))
        return 3 * ((1 - t)[..., None] ** 2 * (p[1] - p[0])
                    + 2 * (1 - t)[..., None] * t[..., None] * (p[2] - p[1])
                    + t[..., None] ** 2 * (p[3] - p[2]))

    def second_derivative(self, t):
        t = np.asarray(t, dtype=float)
        if self.kind == "arc":
            span = self.arc["theta1"] - self.arc["theta0"]
            theta = self.arc["theta0"] + t * span
            return self.arc["radius"] * span ** 2 * np.stack(
                [-np.cos(theta), -np.sin(theta)], axis=-1)
        p = self.cps
        if self.kind == "line":
            return np.broadcast_to(np.zeros(2), t.shape + (2,)).copy()
        if self.kind == "quad":
            second = p[2] - 2 * p[1] + p[0]
            return np.broadcast_to(2 * second, t.shape + (2,)).copy()
        return 6 * ((1 - t)[..., None] * (p[2] - 2 * p[1] + p[0])
                    + t[..., None] * (p[3] - 2 * p[2] + p[1]))

    def curvature_grid(self, t):
        """Signed curvature at one or many parameters."""
        first = self.derivative(t)
        second = self.second_derivative(t)
        cross = first[..., 0] * second[..., 1] - first[..., 1] * second[..., 0]
        speed = np.linalg.norm(first, axis=-1)
        return cross / np.maximum(speed ** 3, 1e-12)

    def length(self):
        if self.kind == "arc":
            return self.arc["radius"] * abs(self.arc["theta1"] - self.arc["theta0"])
        if self.kind == "line":
            return float(np.linalg.norm(self.cps[1] - self.cps[0]))
        # 32-node Gauss-Legendre quadrature on |B'(t)|; exact enough for the
        # non-degenerate curves used by garments.
        nodes = 0.5 * (_GL_T + 1.0)
        speeds = np.linalg.norm(self.derivative(nodes), axis=1)
        return 0.5 * float(_GL_W @ speeds)

    def ilength(self, distance, tolerance: float = 1e-12):
        """Parameter t whose arc length from 0 equals ``distance``."""
        if self.kind in ("line", "arc"):
            total = self.length()
            return 0.0 if total <= 0 else min(max(distance / total, 0.0), 1.0)
        total = self.length()
        target = min(max(distance, 0.0), total)
        low, high = 0.0, 1.0
        t = target / total
        for _ in range(100):
            error = self._length_to(t) - target
            if abs(error) < tolerance:
                return t
            if error > 0:
                high = t
            else:
                low = t
            speed = float(np.linalg.norm(self.derivative(t)))
            step = -error / speed if speed > 1e-12 else 0.0
            candidate = min(max(t + step, low), high)
            if not low < candidate < high:
                candidate = 0.5 * (low + high)
            if abs(candidate - t) < 1e-15:
                return candidate
            t = candidate
        return t

    def _length_to(self, t):
        nodes = 0.5 * t * (_GL_T + 1.0)
        speeds = np.linalg.norm(self.derivative(nodes), axis=1)
        return 0.5 * t * float(_GL_W @ speeds)


def _arc_bulge(centre, radius: float, theta_a: float, theta_b: float) -> float:
    """Signed bulge (sagitta / half-chord) of the arc between two angles."""
    centre = np.asarray(centre, dtype=float)
    start = centre + radius * np.array([math.cos(theta_a), math.sin(theta_a)])
    end = centre + radius * np.array([math.cos(theta_b), math.sin(theta_b)])
    middle = centre + radius * np.array(
        [math.cos((theta_a + theta_b) / 2.0), math.sin((theta_a + theta_b) / 2.0)])
    chord = end - start
    chord_length = float(np.linalg.norm(chord))
    if chord_length <= 1e-12:
        return 0.0
    left = np.array([-chord[1], chord[0]]) / chord_length
    sagitta = float((middle - 0.5 * (start + end)) @ left)
    return sagitta / (chord_length / 2.0)


def _signed_angle(v1, v2) -> float:
    """Signed angle from ``v1`` to ``v2`` (2D, scalar cross product)."""
    a = np.asarray(v1, dtype=float)
    b = np.asarray(v2, dtype=float)
    return math.atan2(a[0] * b[1] - a[1] * b[0], a @ b)


def arc_segments(start, end, radius, large_arc, sweep):
    """Circular arc from SVG-style flags as one or more ``Arc`` segments.

    An SVG arc may span more than 180 degrees, which the editor's ``Arc``
    primitive cannot express in one piece, so it is split at <=180-degree
    intervals.
    """
    curve = NCurve.arc_from_flags(start, end, radius, large_arc, sweep)
    centre = curve.arc["centre"]
    r = curve.arc["radius"]
    theta0 = curve.arc["theta0"]
    span = curve.arc["theta1"] - theta0
    pieces = max(1, int(math.ceil(abs(span) / math.pi - 1e-9)))
    result = []
    for index in range(pieces):
        a = theta0 + span * index / pieces
        b = theta0 + span * (index + 1) / pieces
        p0 = centre + r * np.array([math.cos(a), math.sin(a)])
        p1 = centre + r * np.array([math.cos(b), math.sin(b)])
        result.append(arc_segment(tuple(p0), tuple(p1), _arc_bulge(centre, r, a, b)))
    return result


def arc_segments_through(start, end, point, relative: bool = False):
    """Circular arc through three points, using GarmentCode's factory rules."""
    if relative:
        point = rel_to_abs_2d(start, end, point)
    s = np.asarray(start, dtype=float)
    e = np.asarray(end, dtype=float)
    p = np.asarray(point, dtype=float)
    a, b, c = s, p, e
    determinant = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1])
                         + c[0] * (a[1] - b[1]))
    if abs(determinant) <= 1e-12:
        return [line_segment(start, end)]
    norm_a, norm_b, norm_c = a @ a, b @ b, c @ c
    centre = np.array([
        (norm_a * (b[1] - c[1]) + norm_b * (c[1] - a[1]) + norm_c * (a[1] - b[1])) / determinant,
        (norm_a * (c[0] - b[0]) + norm_b * (a[0] - c[0]) + norm_c * (b[0] - a[0])) / determinant])
    radius = float(np.linalg.norm(a - centre))
    mid_distance = float(np.linalg.norm(p - 0.5 * (s + e)))
    large_arc = mid_distance > radius
    sweep = _signed_angle(p - s, e - s) > 0.0
    return arc_segments(start, end, radius, large_arc, sweep)


def _levenberg_marquardt(residual, x0, max_iterations: int = 80,
                         tolerance: float = 1e-14):
    """Small Levenberg-Marquardt with a forward-difference Jacobian."""
    x = np.asarray(x0, dtype=float).copy()
    r = residual(x)
    value = float(r @ r)
    damping = 1e-3
    for _ in range(max_iterations):
        jacobian = np.empty((len(r), len(x)))
        # Deliberate loop: one finite-difference column per variable; this is
        # the smallest-possible Jacobian for a 2-3 variable fit.
        for index in range(len(x)):
            step = 1e-7 * max(1.0, abs(x[index]))
            probe = x.copy()
            probe[index] += step
            jacobian[:, index] = (residual(probe) - r) / step
        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ r
        diagonal = np.maximum(np.diag(normal), 1e-9)
        while damping < 1e9:
            try:
                step = np.linalg.solve(normal + damping * np.diag(diagonal), -gradient)
            except np.linalg.LinAlgError:
                damping *= 10.0
                continue
            candidate = x + step
            probe_residual = residual(candidate)
            probe_value = float(probe_residual @ probe_residual)
            if probe_value < value:
                x, r, value = candidate, probe_residual, probe_value
                damping = max(damping / 4.0, 1e-12)
                break
            damping *= 10.0
        else:
            break
        if value < tolerance or np.linalg.norm(step) < 1e-12 * max(1.0, np.linalg.norm(x)):
            break
    return x, r


def curve_match_tangents(control_points, tan0, tan1, target_len=None):
    """Cubic Bezier matching both endpoint tangents.

    The endpoint tangents are satisfied by construction (control points on the
    tangent lines), which collapses GarmentCode's five free offsets into three
    scalars: the two control-point distances and the end extension along the
    chord. The remaining soft goals (length, curvature, end extension) are a
    small smooth least-squares problem.
    """
    cps = np.asarray(control_points, dtype=float)
    p0, c1_initial, c2_initial, p3_initial = cps
    direction = p3_initial - p0
    direction = direction / np.linalg.norm(direction)
    t0 = np.asarray(tan0, dtype=float)
    t0 = t0 / np.linalg.norm(t0)
    t1 = np.asarray(tan1, dtype=float)
    t1 = t1 / np.linalg.norm(t1)
    if target_len is None:
        target_len = NCurve(cps=cps).length()
    parameters = np.linspace(0.0, 1.0, 50)

    def build(x):
        a, b, extension = x
        p3 = p3_initial + extension * direction
        return np.array([p0, p0 + a * t0, p3 - b * t1, p3])

    def residual(x):
        curve = NCurve(cps=build(x))
        return np.concatenate(([curve.length() - target_len],
                               curve.curvature_grid(parameters),
                               [math.sqrt(1e-3) * x[2]]))

    chord = float(np.linalg.norm(p3_initial - p0))
    a0 = max(float((c1_initial - p0) @ t0), 1e-2 * chord)
    b0 = max(float((p3_initial - c2_initial) @ t1), 1e-2 * chord)
    x, _ = _levenberg_marquardt(residual, [a0, b0, 0.0])
    return build(x)


def _clamp_box_qp(matrix, target):
    """Exact minimiser of ``|M l - c|^2`` over ``l`` in [0, 1]^2."""
    def value(l):
        return float(np.linalg.norm(matrix @ l - target) ** 2)

    best = np.clip(np.linalg.lstsq(matrix, target, rcond=None)[0], 0.0, 1.0)
    best_value = value(best)
    for index in (0, 1):
        other = 1 - index
        column = matrix[:, other]
        for fixed in (0.0, 1.0):
            right = target - fixed * matrix[:, index]
            free = float(column @ right) / max(float(column @ column), 1e-18)
            candidate = np.clip(
                np.array([fixed, free]) if index == 0 else np.array([free, fixed]),
                0.0, 1.0)
            candidate_value = value(candidate)
            if candidate_value < best_value:
                best, best_value = candidate, candidate_value
    for first in (0.0, 1.0):
        for second in (0.0, 1.0):
            candidate = np.array([first, second])
            candidate_value = value(candidate)
            if candidate_value < best_value:
                best, best_value = candidate, candidate_value
    return best


def corner_projection(curve1: NCurve, curve2: NCurve, target_vector):
    """Parameters where the vector between two curves matches the target."""
    target = np.asarray(target_vector, dtype=float)
    if curve1.kind == "line" and curve2.kind == "line":
        a1, b1 = curve1.cps
        a2, b2 = curve2.cps
        d1, d2 = b1 - a1, b2 - a2
        matrix = np.column_stack([-d1, d2])
        first, second = _clamp_box_qp(matrix, target - (a2 - a1))
        return float(first), float(second)

    def residual(parameters):
        first = min(max(parameters[0], 0.0), 1.0)
        second = min(max(parameters[1], 0.0), 1.0)
        return curve2.point(second) - curve1.point(first) - target

    x, _ = _levenberg_marquardt(residual, [0.5, 0.5])
    return float(min(max(x[0], 0.0), 1.0)), float(min(max(x[1], 0.0), 1.0))


@dataclass(frozen=True)
class Segment:
    """One boundary piece of a panel between two known points."""

    p0: Vec2
    p1: Vec2
    curve: Curve

    def reversed(self) -> "Segment":
        if isinstance(self.curve, Bezier):
            curve = Bezier(controls=tuple(reversed(self.curve.controls)))
        elif isinstance(self.curve, Arc):
            curve = Arc(bulge=-self.curve.bulge)
        else:
            curve = Line()
        return Segment(self.p1, self.p0, curve)


def line_segment(p0, p1) -> Segment:
    return Segment((float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1])), Line())


def quad_segment(p0, p1, control) -> Segment:
    return Segment((float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1])),
                   Bezier(controls=((float(control[0]), float(control[1])),)))


def arc_segment(p0, p1, bulge: float) -> Segment:
    return Segment((float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1])),
                   Arc(bulge=float(bulge)))


def _ncurve_of(segment: Segment) -> NCurve:
    """The :class:`NCurve` matching a segment, in the segment's units."""
    if isinstance(segment.curve, Arc):
        geometry = segment.curve.geometry(segment.p0, segment.p1)
        if geometry is None:
            return NCurve(cps=[segment.p0, segment.p1])
        centre, radius, theta0, sweep = geometry
        return NCurve(arc=dict(centre=np.asarray(centre, dtype=float), radius=radius,
                               theta0=theta0, theta1=theta0 + sweep))
    points = [segment.p0]
    if isinstance(segment.curve, Bezier):
        points += list(segment.curve.controls)
    points.append(segment.p1)
    return NCurve(cps=points)


def _point_at(segment: Segment, distance: float):
    curve = _ncurve_of(segment)
    return tuple(curve.point(curve.ilength(distance)))


def segment_length(segment: Segment) -> float:
    """Arc length of one segment."""
    return float(_ncurve_of(segment).length())


def _subsegment(segment: Segment, start: float, end: float):
    """The part of a segment between two arc-length positions."""
    total = _ncurve_of(segment).length()
    if end - start <= 1e-12 or total <= 1e-12:
        return None
    if start <= 1e-12:
        first = segment
    else:
        first = split_segment(segment, start / total)[1]
    if end >= total - 1e-12:
        return first
    return split_segment(first, (end - start) / (total - start))[0]


def translate_segment(segment: Segment, delta):
    """Move a segment by ``delta`` (curvature is translation invariant)."""
    dx, dy = float(delta[0]), float(delta[1])
    p0 = (segment.p0[0] + dx, segment.p0[1] + dy)
    p1 = (segment.p1[0] + dx, segment.p1[1] + dy)
    if isinstance(segment.curve, Bezier):
        curve = Bezier(controls=tuple((c[0] + dx, c[1] + dy)
                                      for c in segment.curve.controls))
    elif isinstance(segment.curve, Arc):
        curve = Arc(bulge=segment.curve.bulge)
    else:
        curve = Line()
    return Segment(p0, p1, curve)


def translate_segments(segments, delta):
    # Deliberate comprehension: one moved Python segment per input segment.
    return [translate_segment(segment, delta) for segment in segments]


def reverse_segments(segments):
    return [segment.reversed() for segment in reversed(segments)]


def cut_corner_segments(segments, index, target):
    """Splice a target shape into two consecutive straight corner edges.

    This is the panel-level half of GarmentCode's ``cut_corner``: the two
    corner edges are split at the parameters that fit the target's chord, the
    target is translated there, and the leftovers are reconnected.
    """
    first, second = segments[index], segments[index + 1]
    if not isinstance(first.curve, Line) or not isinstance(second.curve, Line):
        raise TypeError("corner splices need two straight corner edges")
    if float(target[0].p0[1]) > float(target[-1].p1[1]):
        target = translate_segments(
            reverse_segments(target), tuple(-np.asarray(target[-1].p1, dtype=float)))

    swapped = float(first.p0[1]) > float(second.p1[1])
    curve1 = _ncurve_of(second if swapped else first)
    curve2 = _ncurve_of(first if swapped else second)
    chord = np.asarray(target[-1].p1, dtype=float) - np.asarray(target[0].p0, dtype=float)
    location_1, location_2 = corner_projection(curve1, curve2, chord)
    point_1 = curve1.point(location_1)
    placed = translate_segments(target, tuple(point_1 - np.asarray(target[0].p0, dtype=float)))
    if swapped:
        placed = reverse_segments(placed)
        first_location, second_location = location_2, location_1
    else:
        first_location, second_location = location_1, location_2

    left = split_segment(first, first_location)[0]
    right = split_segment(second, second_location)[1]
    left = Segment(left.p0, placed[0].p0, left.curve)
    right = Segment(placed[-1].p1, right.p1, right.curve)
    return segments[:index] + [left] + placed + [right] + segments[index + 2:]


def split_segment(segment: Segment, fraction: float) -> list[Segment]:
    """Split a segment at a fraction of its arc length."""
    fraction = min(max(float(fraction), 0.0), 1.0)
    if isinstance(segment.curve, Line):
        middle = lerp_point(segment.p0, segment.p1, fraction)
        return [line_segment(segment.p0, middle), line_segment(middle, segment.p1)]
    if isinstance(segment.curve, Arc):
        curve = _ncurve_of(segment)
        centre = curve.arc["centre"]
        radius = curve.arc["radius"]
        theta0 = curve.arc["theta0"]
        theta1 = curve.arc["theta1"]
        split = theta0 + fraction * (theta1 - theta0)
        middle = tuple(centre + radius * np.array([math.cos(split), math.sin(split)]))
        return [arc_segment(segment.p0, middle, _arc_bulge(centre, radius, theta0, split)),
                arc_segment(middle, segment.p1, _arc_bulge(centre, radius, split, theta1))]
    if not isinstance(segment.curve, Bezier):
        raise TypeError("only line, Bezier and arc segments can be split")
    controls = list(segment.curve.controls)
    points = [np.asarray(segment.p0, dtype=float)] \
        + [np.asarray(c, dtype=float) for c in controls] \
        + [np.asarray(segment.p1, dtype=float)]
    curve = NCurve(cps=points)
    t = curve.ilength(fraction * curve.length())
    p0, p1 = points[0], points[-1]
    if len(controls) == 1:
        control = points[1]
        a = np.asarray(lerp_point(p0, control, t))
        b = np.asarray(lerp_point(control, p1, t))
        middle = np.asarray(lerp_point(a, b, t))
        return [quad_segment(tuple(p0), tuple(middle), tuple(a)),
                quad_segment(tuple(middle), tuple(p1), tuple(b))]
    c1, c2 = points[1], points[2]
    a0 = np.asarray(lerp_point(p0, c1, t))
    a1 = np.asarray(lerp_point(c1, c2, t))
    a2 = np.asarray(lerp_point(c2, p1, t))
    b0 = np.asarray(lerp_point(a0, a1, t))
    b1 = np.asarray(lerp_point(a1, a2, t))
    middle = np.asarray(lerp_point(b0, b1, t))
    left = Segment(tuple(p0), tuple(middle),
                   Bezier(controls=(tuple(a0), tuple(b0))))
    right = Segment(tuple(middle), tuple(p1),
                    Bezier(controls=(tuple(b1), tuple(a2))))
    return [left, right]


def insert_notches(segment: Segment, notches, interior) -> list[Segment]:
    """Cut V-shaped notches into a segment (straight or curved).

    ``notches`` is an iterable of ``(centre_distance, width, depth)`` measured
    along the segment from ``p0``. The apex of each V is pushed towards
    ``interior``. This is the geometric part of GarmentCode's dart/slit
    insertion: the piece of the base segment between the two notch corners is
    replaced by two straight edges, exactly like ``cut_into_edge``. The stitch
    bookkeeping is intentionally not ported.
    """
    total = _ncurve_of(segment).length()
    if total <= 1e-12:
        return [segment]

    # Deliberate generator: sorting a handful of Python tuples has to preserve
    # the (centre, width, depth) records, so numpy cannot sort it in place.
    ordered = sorted(
        (float(centre), float(width), float(depth)) for centre, width, depth in notches)
    pieces = []
    cursor = 0.0
    for centre, width, depth in ordered:
        start = min(max(centre - width / 2.0, cursor), total)
        end = min(max(centre + width / 2.0, start), total)
        if start > cursor:
            base = _subsegment(segment, cursor, start)
            if base is not None:
                pieces.append(base)
        corner_a = _point_at(segment, start)
        corner_b = _point_at(segment, end)
        chord = np.asarray(corner_b, dtype=float) - np.asarray(corner_a, dtype=float)
        chord_length = float(np.linalg.norm(chord))
        if chord_length <= 1e-12:
            cursor = end
            continue
        normal = np.array([-chord[1], chord[0]]) / chord_length
        middle = 0.5 * (np.asarray(corner_a) + np.asarray(corner_b))
        if normal @ (np.asarray(interior, dtype=float) - middle) < 0:
            normal = -normal
        apex = tuple(middle + normal * depth)
        pieces.append(line_segment(corner_a, apex))
        pieces.append(line_segment(apex, corner_b))
        cursor = end
    if cursor < total - 1e-12:
        base = _subsegment(segment, cursor, total)
        if base is not None:
            pieces.append(base)
    return pieces or [segment]


def segments_to_panel(name: str, segments, scale: float = 1.0,
                      edge_names: dict | None = None) -> PanelSpec:
    """Turn a closed segment chain into a counter-clockwise ``PanelSpec``.

    ``edge_names`` maps an *original* segment index to the label its editor
    edge should carry (for the generator's internal seams). The mapping is
    resolved after the optional clockwise-to-counter-clockwise reversal.
    """
    if not segments:
        raise ValueError("a panel needs at least one segment")
    indexed = list(enumerate(segments))
    # GarmentCode builds panels clockwise; this library requires CCW.
    corners = [(segment.p0[0], segment.p0[1]) for _, segment in indexed]
    if signed_area(corners) < 0:
        indexed = [(index, segment.reversed()) for index, segment in reversed(indexed)]

    # Deliberate comprehensions: the vertex list and the edge records are
    # Python objects, which numpy cannot build.
    vertices = [(segment.p0[0] * scale, segment.p0[1] * scale) for _, segment in indexed]
    edges = []
    last = len(indexed) - 1
    for position, (original_index, segment) in enumerate(indexed):
        curve = segment.curve
        if isinstance(curve, Bezier):
            curve = Bezier(controls=tuple(
                (control[0] * scale, control[1] * scale) for control in curve.controls))
        elif isinstance(curve, Arc):
            curve = Arc(bulge=curve.bulge)
        else:
            curve = Line()
        label = "" if not edge_names else edge_names.get(original_index, "")
        edges.append(EdgeSpec(position, 0 if position == last else position + 1,
                              curve, label))
    return PanelSpec(name=name, vertices=vertices, edges=edges)
