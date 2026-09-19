"""Per-vertex strain, the quantity the pattern editor's stress display shows.

The engine does not report a per-vertex stress today: `get_debug_colors()`
carries the collision-debug marks (grey for untouched vertices, yellow where a
collision pair was found). The editor therefore derives its own measure from the
two vertex sets it already has - the rest positions in the ``QYBasis`` shape key
and the simulated positions the engine wrote into ``QYSim``:

    strain(vertex) = mean over the vertex's edges of (sim_length / rest_length - 1)

That is the same measure this project reports as stretch when it compares
simulated area against the pattern's area, so the display and the recorded
numbers agree. Positive values are stretched, negative are compressed, and zero
is the flat pattern.

Everything here is plain numpy: no Blender data and no GPU, so the mapping can
be checked outside a viewport.
"""

from __future__ import annotations

import numpy as np

# The display saturates at these strains: a panel stretched by 20% or compressed
# by 10% from its rest shape is drawn at the end of the ramp. The numbers follow
# the engine's own measurements, where a settled garment shows a 1.1-1.4 area
# ratio against the pattern (see the real-time performance record), so a ramp
# that saturates much below 0.2 would paint every settled garment fully red.
MIN_STRAIN = -0.1
MAX_STRAIN = 0.2

# Rest, compressed and stretched colours of the ramp.
REST_COLOR = (0.25, 0.72, 0.30)
COLD_COLOR = (0.20, 0.45, 0.90)
HOT_COLOR = (0.90, 0.22, 0.15)


def edge_strain(rest, sim, edges) -> np.ndarray:
    """Relative length change of every edge, as a float32 array.

    ``rest`` and ``sim`` are (N, 3) vertex arrays in the same space and ``edges``
    is an (E, 2) index array. An edge whose rest length is zero keeps a strain of
    zero instead of dividing by it.
    """
    rest = np.asarray(rest, dtype=np.float32).reshape(-1, 3)
    sim = np.asarray(sim, dtype=np.float32).reshape(-1, 3)
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    if edges.size == 0 or rest.shape != sim.shape:
        return np.zeros(len(edges), dtype=np.float32)
    rest_length = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    sim_length = np.linalg.norm(sim[edges[:, 0]] - sim[edges[:, 1]], axis=1)
    strain = np.zeros(len(edges), dtype=np.float32)
    valid = rest_length > 1e-9
    strain[valid] = sim_length[valid] / rest_length[valid] - 1.0
    return strain


def vertex_strain(rest, sim, edges) -> np.ndarray:
    """Mean strain of every vertex, as a float32 array of length N.

    A vertex with no valid edge reads as zero (rest).
    """
    rest = np.asarray(rest, dtype=np.float32).reshape(-1, 3)
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    strain = edge_strain(rest, sim, edges)
    if edges.size == 0 or len(rest) == 0:
        return np.zeros(len(rest), dtype=np.float32)
    # One bincount per array: a vertex's strain is the mean over its edges, and
    # bincount is the vectorised way to accumulate them without a Python loop.
    flat = edges.reshape(-1)
    sums = np.bincount(flat, weights=np.repeat(strain, 2).astype(np.float64),
                       minlength=len(rest))
    counts = np.bincount(flat, minlength=len(rest)).astype(np.float64)
    return np.divide(sums, counts, out=np.zeros(len(rest), dtype=np.float64),
                     where=counts > 0).astype(np.float32)


def strain_colors(strain, min_strain: float = MIN_STRAIN,
                  max_strain: float = MAX_STRAIN) -> np.ndarray:
    """Strain as an (N, 4) float32 colour array on the documented ramp.

    Blue is compression, green is the rest shape and red is stretch. The alpha
    is 1: the display mode decides how transparent the filled panel is.
    """
    strain = np.asarray(strain, dtype=np.float32).reshape(-1)
    colors = np.empty((len(strain), 4), dtype=np.float32)

    hot = np.array(HOT_COLOR, dtype=np.float32)
    cold = np.array(COLD_COLOR, dtype=np.float32)
    rest = np.array(REST_COLOR, dtype=np.float32)

    positive = strain >= 0.0
    t_hot = np.clip(strain / max(max_strain, 1e-6), 0.0, 1.0)
    t_cold = np.clip(strain / min(min_strain, -1e-6), 0.0, 1.0)

    # Rest to red on the stretched side, rest to blue on the compressed side.
    colors[:, :3] = np.where(positive[:, None],
                             rest + (hot - rest) * t_hot[:, None],
                             rest + (cold - rest) * t_cold[:, None])
    colors[:, 3] = 1.0
    return colors
