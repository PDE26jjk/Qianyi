"""Deterministic decorative runs."""

from __future__ import annotations

import numpy as np

from .curves import Polyline, Vec2, as_vec2, left_normal


def noise_run(
    a: Vec2,
    b: Vec2,
    amplitude: float,
    wavelength: float,
    samples: int,
    seed: int,
) -> Polyline:
    """A straight run turned into a ragged polyline.

    The offsets come from a seeded generator, so the same seed always produces
    the same run, and they are windowed to vanish at both ends: a noisy edge
    still meets its neighbours exactly.

    ``amplitude`` is in millimetres, ``wavelength`` in millimetres along the
    run; ``samples`` is the number of points, and ``seed`` may be any integer.
    """
    count = max(int(samples), 2)
    start = np.asarray(as_vec2(a), dtype=float)
    end = np.asarray(as_vec2(b), dtype=float)
    chord = end - start
    length = float(np.hypot(chord[0], chord[1]))
    if length <= 1e-9:
        return Polyline(points=(as_vec2(a), as_vec2(b)))

    t = np.linspace(0.0, 1.0, count)
    if wavelength > 0.0:
        waves = max(1.0, length / float(wavelength))
    else:
        waves = 1.0
    phase = t * waves * 2.0 * np.pi
    window = np.sin(np.pi * t) ** 2
    rng = np.random.default_rng(abs(int(seed)))
    jitter = rng.normal(0.0, 1.0, count)
    offset = float(amplitude) * window * jitter

    normal = left_normal(as_vec2(a), as_vec2(b))
    points = start[None, :] + t[:, None] * chord[None, :] + offset[:, None] * normal[None, :]
    points[0] = start
    points[-1] = end
    return Polyline(points=tuple((float(p[0]), float(p[1])) for p in points))
