"""Arc-length sampling and spline fitting for the pattern geometry commands.

The editor holds a curve in one of three forms: a straight two-point edge, a
Bezier (two points plus handles) and a cubic spline through interpolation
points. A command that reshapes an edge measures along the sampled curve and
writes its result back as a spline through a few control points, which is what
`fit_control_points` produces. The straight and the exactly-representable cases
are decisions of the caller, not of the fitter: a fit that needs two control
points describes a straight piece, and a command that produces an exact circle
keeps the Bezier that reproduces it.
"""

from __future__ import annotations

import numpy as np

from .geometric_operation import generate_curve_points

# The target curve is reduced to this many samples before fitting. A piece is at
# least the merge threshold long, so this resolves every piece a command can
# produce, and it keeps the greedy search below cheap: the error measurement is
# a distance matrix of (samples x samples * ERROR_OVERSAMPLING).
FIT_TARGET_SAMPLES = 129
# The candidate spline is sampled this many times per target sample, so the
# error sees the spline's deviation between the target's samples too.
FIT_ERROR_OVERSAMPLING = 8


def cumulative_length(points) -> np.ndarray:
    """The arc length up to each point of a polyline, starting at zero."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 2:
        return np.zeros(len(points), dtype=np.float64)
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.concatenate(([0.0], np.cumsum(steps)))


def polyline_length(points) -> float:
    """The total arc length of a polyline."""
    lengths = cumulative_length(points)
    return float(lengths[-1]) if len(lengths) else 0.0


def point_at_length(points, distance: float) -> np.ndarray:
    """The polyline point at one arc length, interpolated between samples."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) == 0:
        raise ValueError("a polyline needs at least one point")
    if len(points) == 1:
        return points[0].copy()
    lengths = cumulative_length(points)
    total = lengths[-1]
    distance = min(max(float(distance), 0.0), total)
    return np.array((np.interp(distance, lengths, points[:, 0]),
                     np.interp(distance, lengths, points[:, 1])), dtype=np.float64)


def resample_by_arc_length(points, count: int) -> np.ndarray:
    """``count`` points at equal arc length along a polyline, ends included."""
    points = np.asarray(points, dtype=np.float64)
    if count < 2 or len(points) < 2:
        return points.copy()
    lengths = cumulative_length(points)
    total = lengths[-1]
    if total <= 0.0:
        return np.repeat(points[:1], count, axis=0)
    targets = np.linspace(0.0, total, count)
    return np.column_stack((np.interp(targets, lengths, points[:, 0]),
                            np.interp(targets, lengths, points[:, 1])))


def slice_by_arc_length(points, start: float, end: float) -> np.ndarray:
    """The part of a polyline between two arc lengths, ends interpolated."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 2:
        return points.copy()
    lengths = cumulative_length(points)
    total = lengths[-1]
    start = min(max(float(start), 0.0), total)
    end = min(max(float(end), 0.0), total)
    if end < start:
        start, end = end, start
    inner = points[(lengths > start) & (lengths < end)]
    first = point_at_length(points, start)
    last = point_at_length(points, end)
    if len(inner) == 0:
        return np.vstack((first, last))
    return np.vstack((first, inner, last))


def evaluate_control_points(control_points, sample_count: int) -> np.ndarray:
    """The polyline a spline through these control points is drawn as.

    This is the same code path `Edge2D.render_points` uses for a spline edge,
    so a fit is measured against the curve the editor will show.
    """
    control_points = np.asarray(control_points, dtype=np.float64)
    if len(control_points) < 2:
        return control_points.copy()
    if len(control_points) == 2:
        # generate_curve_points returns a two-point edge untouched, which would
        # make the error measurement blind between the two ends.
        return resample_by_arc_length(control_points, sample_count)
    return np.asarray(generate_curve_points(control_points, None, None, sample_count),
                      dtype=np.float64)


def deviation_at_length(target, samples) -> np.ndarray:
    """The distance between a target and a fit at each equal-arc-length point.

    `target` is already an equal-arc-length sampling of the piece, and the fit's
    own samples are resampled onto the same parameterisation before the two are
    compared point by point. That sees a deviation wherever it lies - between
    the target's samples as well as on them - and it costs one pass instead of a
    distance matrix of every sample against every sample, which is what made a
    curved piece expensive to fit. A fit that only slid along its own curve
    would read as an error here, and one of ours cannot slide: its ends are
    pinned to the piece it came from, so the measurement is conservative rather
    than loose.
    """
    target = np.asarray(target, dtype=np.float64)
    if len(target) == 0:
        return np.zeros(0, dtype=np.float64)
    fit = resample_by_arc_length(samples, len(target))
    return np.sqrt(((target - fit) ** 2).sum(axis=1))


def fit_control_points(points, tolerance: float, max_points: int):
    """Fit a spline through a few of ``points`` within ``tolerance``.

    Returns ``(control_points, reached, error)``: control points taken from the
    polyline (ends included, so the piece stays attached), whether the fit
    reached the tolerance, and the error it reached. Two control points mean the
    piece is straight within the tolerance. When no fit reaches the tolerance
    within ``max_points``, the closest fit found is returned and ``reached`` is
    False, so the caller keeps the best shape it has instead of refusing.

    The control points are first taken at equal arc length, one count at a time,
    because an interpolating spline answers that with a smoothly decreasing
    error; when that is not enough, the sample the fit misses by the most is
    added while it helps, which is what covers a piece with a local feature. The
    error is the fit's distance from the piece at equal arc length, so it is
    measured where the deviation actually is rather than only at the samples the
    control points were chosen from.
    """
    target = resample_by_arc_length(points, min(FIT_TARGET_SAMPLES, max(len(points), 2)))
    count = len(target)
    if count < 2:
        raise ValueError("a fit needs at least two points")
    if count == 2:
        return target, True, 0.0

    # The candidate fit is sampled this many times per target sample, so its own
    # arc length is measured accurately when the two are compared.
    sample_count = max(count * FIT_ERROR_OVERSAMPLING, 32)

    def measure(indices):
        """The deviation of the fit, and the target point it missed the most."""
        fit = evaluate_control_points(target[indices], sample_count)
        deviations = deviation_at_length(target, fit)
        return float(deviations.max()), int(deviations.argmax())

    best = None
    # loop: one fit per control point count, from two up to the cap
    for number in range(2, max_points + 1):
        selected = [int(index) for index in np.unique(np.linspace(0, count - 1, number).astype(int))]
        error, _ = measure(selected)
        if best is None or error < best[0]:
            best = (error, selected)
        if error <= tolerance:
            return target[selected], True, error

    error, selected = best
    # loop: the refinement adds one point per round, and stops when a round
    # cannot improve the fit any further
    while error > tolerance and len(selected) < max_points:
        _, index = measure(selected)
        if index in selected:
            break
        candidate = sorted(selected + [index])
        new_error, _ = measure(candidate)
        if new_error >= error:
            break
        error, selected = new_error, candidate
    return target[selected], error <= tolerance, error
