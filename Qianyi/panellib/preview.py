"""Thumbnails for the library panel: a panel outline drawn into an RGBA buffer."""

from __future__ import annotations

import numpy as np

from .land import LandedPanel, landed_boundary

BACKGROUND = np.array((0.16, 0.16, 0.18, 1.0), dtype=np.float32)
OUTLINE = np.array((0.85, 0.86, 0.90, 1.0), dtype=np.float32)


def render_preview(panels: list[LandedPanel], size: int = 96) -> np.ndarray:
    """Rasterise the boundaries of ``panels`` into a ``(size, size, 4)`` image.

    The outline is scattered into pixels and then thickened with a 3x3
    dilation, so the whole thing is numpy work: no per-pixel Python loop.
    """
    size = int(size)
    image = np.tile(BACKGROUND, (size, size, 1))
    boundaries = [landed_boundary(panel, per_edge=24) for panel in panels]
    boundaries = [points for points in boundaries if points.size > 0]
    if not boundaries:
        return image

    all_points = np.concatenate(boundaries, axis=0)
    minimum = all_points.min(axis=0)
    maximum = all_points.max(axis=0)
    extent = np.maximum(maximum - minimum, 1e-6)
    margin = size * 0.12
    scale = (size - 2.0 * margin) / extent.max()

    mask = np.zeros((size, size), dtype=bool)
    for points in boundaries:
        pixels = (points - minimum) * scale + margin
        # Flip Y so the panel is not drawn upside down in the thumbnail.
        columns = np.clip(np.rint(pixels[:, 0]).astype(np.int64), 0, size - 1)
        rows = np.clip(np.rint(size - 1 - pixels[:, 1]).astype(np.int64), 0, size - 1)
        mask[rows, columns] = True

    mask = _dilate(mask)
    image[mask] = OUTLINE
    return image


def _dilate(mask: np.ndarray) -> np.ndarray:
    """3x3 binary dilation with shifted copies instead of a neighbourhood loop."""
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def to_pixels(image: np.ndarray) -> np.ndarray:
    """Flatten to the (N,) float sequence a Blender image expects."""
    return np.asarray(image, dtype=np.float32).reshape(-1)
