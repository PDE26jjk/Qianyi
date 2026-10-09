import math

import bpy
import gpu
import mathutils
import numpy as np
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from .. import global_data
from .base_renderer import BaseRenderer
from ..utilities.console import console_print, console
from ..utilities.coords_transform import create_2d_matrix


# One connector every this many millimetres of sewing, so a short chain still
# gets a couple of lines and a long one does not turn into a solid block. The
# ends are always sampled, they are the lines that show where the sewing starts
# and ends.
STITCH_LINE_STEP_MM = 15.0
STITCH_LINE_SEGMENTS_MAX = 32

# The connectors are a reading aid, not the sewing itself: draw them thinner
# than the sewing so a selected chain stays readable.
STITCH_LINE_WIDTH = 1.0

# A seam whose two sides cannot be paired is drawn in this color instead of its
# own: it takes its patterns out of the mesh and the simulation, so it has to be
# visible as the thing to fix.
BROKEN_SEAM_COLOR = (1.0, 0.15, 0.1)


def polyline_length(points):
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1).sum())


def side_points_and_steps(polylines):
    """One side's drawn points, and the arc length of each over the whole side.

    A side is several polylines - one per drawn span - so the arc length runs
    over the concatenation of them: 0 is the start of the first span and the
    last value the end of the last one. Two spans that meet put the same length
    twice in the array, once for each of the two points: a fraction strictly
    between two spans is read from the array, and a fraction that lands on a span
    boundary is read from the spans themselves (`run_end_points`), because
    `np.interp` over a repeated length answers with the later point.
    """
    points = np.concatenate([np.asarray(polyline, dtype=np.float64)
                             for polyline in polylines], axis=0)
    runs = []
    walked = 0.0
    for polyline in polylines:  # loop: one drawn span's own arc length per step
        pts = np.asarray(polyline, dtype=np.float64)
        steps = np.concatenate(([0.0], np.cumsum(
            np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1))))
        runs.append(steps + walked)
        walked += float(steps[-1])
    return points, np.concatenate(runs)


def sample_side(polylines, fractions):
    """Positions at the given arc-length fractions of one whole side."""
    points, steps = side_points_and_steps(polylines)
    total = float(steps[-1])
    if total <= 0.0:
        return np.repeat(points[:1], len(fractions), axis=0)
    targets = np.asarray(fractions, dtype=np.float64) * total
    sampled = np.empty((len(fractions), points.shape[1]), dtype=np.float64)
    for axis in range(points.shape[1]):  # loop: one coordinate per interpolation
        sampled[:, axis] = np.interp(targets, steps, points[:, axis])
    return sampled


def span_fractions(polylines):
    """Where a side's drawn runs begin and end, as fractions of its own length."""
    extents, _total = run_extents(polylines)
    return [value for start, end, _points in extents for value in (start, end)]


def run_extents(polylines):
    """Each drawn run's own polyline, under the fraction range it covers.

    A side is one polyline per drawn run, in the order it is stitched, so a run
    boundary is the arc length walked before it over the side's whole length.
    Returns ``(extents, total_length)``, where each extent is ``(start, end,
    points)``: reading a run's own polyline is what keeps the point at the end of
    one run and the point at the start of the next - the same fraction of the
    side, two different points where the runs do not share a vertex - apart.
    """
    lengths = [polyline_length(part) for part in polylines]
    total = float(sum(lengths))
    if total <= 0.0:
        return [], 0.0
    extents = []
    walked = 0.0
    for points, length in zip(polylines, lengths):  # loop: one drawn run per step
        extents.append((walked / total, (walked + length) / total,
                        np.asarray(points, dtype=np.float64)))
        walked += length
    return extents, total


def run_end_points(extents, fraction, tolerance=1e-9):
    """The ends of drawn runs that sit at one fraction of the side, in run order.

    A run that begins there answers with its own first point and a run that ends
    there with its own last one, so the two sides of a join are the two points
    the runs were drawn between.
    """
    ends = []
    for start, end, points in extents:  # loop: one drawn run per step
        if len(points) == 0:
            continue
        if abs(start - fraction) <= tolerance:
            ends.append(points[0])
        if abs(end - fraction) <= tolerance:
            ends.append(points[-1])
    return ends


def unique_points(points):
    """The points, each one once: two runs that meet at one vertex are one end."""
    seen = []
    for point in points:  # loop: one end of one run per step
        if any(float(np.linalg.norm(np.asarray(point[:2]) - np.asarray(other[:2])))
               <= 1e-9 for other in seen):
            continue
        seen.append(point)
    return seen


def span_breaks(polylines1, polylines2, tolerance=1e-6):
    """Every fraction either side has a drawn run begin or end at."""
    values = sorted({0.0, 1.0, *span_fractions(polylines1),
                     *span_fractions(polylines2)})
    places = []
    for value in values:  # loop: one breakpoint per step, merged with a tolerance
        if not places or value - places[-1] > tolerance:
            places.append(value)
    return places


def connector_fractions(polylines1, polylines2, tolerance=1e-6):
    """Where along the two sides the connecting lines are drawn.

    Every place either side has a drawn run begin or end is one of the
    connectors, so a run's two ends are joined to the points they are paired
    with: the points at the same fraction of the other side, which is the
    correspondence the merge stitches. Between two such places the lines are
    equally spaced, and how many there are follows the shorter side, so a seam is
    never denser than the shorter of the two.
    """
    places = span_breaks(polylines1, polylines2, tolerance)
    if len(places) < 2:
        places = [0.0, 1.0]
    shortest = min(sum(polyline_length(part) for part in polylines1),
                   sum(polyline_length(part) for part in polylines2))
    counts = []
    for start, end in zip(places, places[1:]):
        lines = int(round((end - start) * shortest / STITCH_LINE_STEP_MM))
        counts.append(max(1, lines))
    total = sum(counts)
    if total > STITCH_LINE_SEGMENTS_MAX:
        # Thin them out together, but never below one line in a piece: the place
        # a run begins or ends at is what these lines are there to show.
        scale = STITCH_LINE_SEGMENTS_MAX / float(total)
        counts = [max(1, int(round(count * scale))) for count in counts]
    fractions = [places[0]]
    for (start, end), count in zip(zip(places, places[1:]), counts):
        fractions.extend(np.linspace(start, end, count + 1)[1:].tolist())
    return fractions


def breakpoint_connectors(polylines1, extents1, polylines2, extents2, fraction):
    """The lines at one place a drawn run of either side begins or ends.

    A run's end is read from that run's own polyline, never by sampling the side
    at the fraction, so a line starts exactly where its run stops. Where both
    sides have a run end at the place - or one has two and the other one, which
    is two runs meeting one - the ends are joined: the one point meets both ends
    of the other side, in the order the runs were drawn.
    """
    ends1 = run_end_points(extents1, fraction)
    ends2 = run_end_points(extents2, fraction)
    ends1, ends2 = unique_points(ends1), unique_points(ends2)
    if not ends1:
        ends1 = [sample_side(polylines1, [fraction])[0]]
    if not ends2:
        ends2 = [sample_side(polylines2, [fraction])[0]]
    if len(ends1) == 1 or len(ends2) == 1:
        return [(point1, point2) for point1 in ends1 for point2 in ends2]
    return list(zip(ends1, ends2))


def connector_lines(polylines1, polylines2):
    """The connecting lines across a sewing, in the patterns' own coordinates.

    One line per place either side's drawn runs begin or end, and equally spaced
    lines in between. The ends come from the runs themselves and the lines
    between them are sampled at the same fraction of each side, which is the
    correspondence the merge stitches - both read from the curves, so what a
    pattern's mesh was sampled into never shows in them.
    """
    if not polylines1 or not polylines2:
        return []
    extents1, _total1 = run_extents(polylines1)
    extents2, _total2 = run_extents(polylines2)
    if not extents1 or not extents2:
        return []
    breaks = span_breaks(polylines1, polylines2)
    lines = []
    # A list of pairs of points, one per connecting line, which is what the batch
    # builder takes.
    for fraction in connector_fractions(polylines1, polylines2):
        if any(abs(fraction - value) <= 1e-9 for value in breaks):
            lines.extend(breakpoint_connectors(polylines1, extents1,
                                               polylines2, extents2, fraction))
        else:
            lines.append((sample_side(polylines1, [fraction])[0],
                          sample_side(polylines2, [fraction])[0]))
    return lines


def stitch_connector_points(pattern1, polylines1, pattern2, polylines2):
    """The connecting lines across a sewing, in view space.

    One line per place either side's drawn runs begin or end, from the point the
    run itself stops at to the point it is paired with, and equally spaced lines
    between those places. A long side facing two short ones draws a line to each
    of their facing ends where they meet it, which is the join the stitches make.
    """
    positions = []
    # A list of the batch's own positions, two per connector sample: one Python
    # object per line, which is what the batch builder takes.
    for point1, point2 in connector_lines(polylines1, polylines2):
        # loop: one connecting line per step
        positions.append(pattern1.pattern_to_view_pos(point1))
        positions.append(pattern2.pattern_to_view_pos(point2))
    return positions


class SewingRenderer(BaseRenderer):
    identity_attribute = "sewing_uuid"

    def __init__(self, sewing):
        super().__init__()
        self.batch_edges1 = None
        self.batch_edges2 = None
        self.batch_stitch_lines = None
        self.sewing_uuid = sewing.global_uuid

    @property
    def sewing(self):
        return global_data.get_obj_by_uuid(self.sewing_uuid, False)

    def ensure_batch(self) -> bool:
        """Whether the batches this renderer draws with are there.

        A seam whose batch was never built - the renderer is made before the two
        sides are walked, and a side the walk refuses leaves it without points -
        has to ask the seam to build again, and then say so if it still cannot.
        Drawing a batch that is not there raises inside the draw callback on
        every frame, which is what takes the editor's own drawing down with it.
        """
        if self.batch_edges1:
            return True
        sewing = self.sewing
        if sewing is None:
            return False
        sewing.need_render_update = True
        try:
            sewing.update()
        except ValueError as refused:
            console.warning("sewing renderer:", refused)
            return False
        return bool(self.batch_edges1)

    def update_batch_edges(self, render_points1, render_points2):
        """One batch per drawn span, for both sides."""
        # A batch per polyline: the spans of one side are not contiguous, so a
        # single LINE_STRIP over them would draw a line across the pattern.
        self.batch_edges1 = [batch_for_shader(self.shader, 'LINE_STRIP',
                                              {"pos": points})
                             for points in render_points1]
        self.batch_edges2 = [batch_for_shader(self.shader, 'LINE_STRIP',
                                              {"pos": points})
                             for points in render_points2]
        p1 = self.sewing.pattern1
        p2 = self.sewing.pattern2
        if p1 is None or p2 is None:
            # A seam whose pattern is gone has nothing to draw; the seam is what
            # the editor drops, this only keeps the frame alive until it does.
            return
        # Both sides are drawn as their polylines whatever their direction:
        # calc_sewing_side_render_points normalises the sampling order, so the
        # drawn polyline cannot carry the direction. The correspondence is
        # shown only by the connectors below, from the sample order, which is
        # the order the spans were created in.
        self.batch_stitch_lines = batch_for_shader(
            self.shader, 'LINES',
            {"pos": stitch_connector_points(p1, render_points1, p2, render_points2)},
        )

    def draw(self, dashed_line=False, alpha=1.0):
        """Draw both halves of this seam in the seam's own colour.

        `alpha` below 1 is how a seam selected in the sewing mode is drawn
        while another mode is active: the same chain, dimmed, so the selection
        stays visible.
        """
        if not self.shader:
            return
        if not self.ensure_batch():
            return
        gpu.state.blend_set('ALPHA')
        self.shader.bind()
        color = BROKEN_SEAM_COLOR if self.sewing.stitch_error else self.sewing.color
        self.shader.uniform_float("color", (*color, alpha))
        p1 = self.sewing.pattern1
        p2 = self.sewing.pattern2
        if p1 is None or p2 is None:
            return
        transform_matrix = p1.calc_matrix()
        self.update_model_matrix(transform_matrix)
        for batch in self.batch_edges1:  # loop: one drawn span per batch
            batch.draw(self.shader)

        transform_matrix = p2.calc_matrix()
        self.update_model_matrix(transform_matrix)
        for batch in self.batch_edges2:  # loop: one drawn span per batch
            batch.draw(self.shader)

        # Only the selected sewing shows how the two sides correspond; drawing
        # them for every chain turned the view into a mesh and made the selected
        # one impossible to pick out.
        if dashed_line and self.batch_stitch_lines is not None:
            previous_width = gpu.state.line_width_get()
            gpu.state.line_width_set(STITCH_LINE_WIDTH)
            self.update_model_matrix(Matrix.Identity(4))
            self.shader.uniform_float("color", (*color, alpha))
            self.batch_stitch_lines.draw(self.shader)
            gpu.state.line_width_set(previous_width)

    def draw_id(self, side1_id=None, side2_id=None):
        """Draw both halves with the ids the pick pass registered for them.

        The ids come from the pass: it is the only thing that knows which pattern
        a half was drawn for, and it records them so a pointer over a half
        resolves back to that side. A caller that passes none gets the side's own
        uuid, which is what this drew before the pass registered halves.
        """
        if not self.shader:
            return
        sewing = self.sewing
        if sewing is None or not self.ensure_batch():
            return

        gpu.state.depth_test_set('NONE')
        manager = global_data.temp_draw_manager

        self.shader.bind()
        p1 = sewing.pattern1
        if p1 is None:
            return
        transform_matrix = p1.calc_matrix()
        self.update_model_matrix(transform_matrix)
        self.shader.uniform_float("color", manager.index_to_rgb(
            sewing.side1.global_uuid if side1_id is None else side1_id))
        for batch in self.batch_edges1:  # loop: one drawn span per batch
            batch.draw(self.shader)

        p2 = sewing.pattern2
        if p2 is None:
            return
        transform_matrix = p2.calc_matrix()
        self.update_model_matrix(transform_matrix)
        self.shader.uniform_float("color", manager.index_to_rgb(
            sewing.side2.global_uuid if side2_id is None else side2_id))
        for batch in self.batch_edges2:  # loop: one drawn span per batch
            batch.draw(self.shader)
