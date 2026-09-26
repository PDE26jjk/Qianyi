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


def sample_polyline(points, fractions):
    """Positions at the given normalized arc-length fractions."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 2:
        return np.repeat(pts[:1], len(fractions), axis=0)
    cumulative = np.concatenate(([0.0], np.cumsum(
        np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1))))
    total = cumulative[-1]
    if total <= 0.0:
        return np.repeat(pts[:1], len(fractions), axis=0)
    targets = np.asarray(fractions, dtype=np.float64) * total
    sampled = np.empty((len(fractions), pts.shape[1]), dtype=np.float64)
    for axis in range(pts.shape[1]):
        sampled[:, axis] = np.interp(targets, cumulative, pts[:, axis])
    return sampled


def stitch_connector_points(pattern1, points1, pattern2, points2):
    """Sampled pairs across a sewing, in view space.

    Both halves are sampled at the same normalized arc length, so the lines
    show how the two sides correspond. The first and the last fraction are
    included: those two pairs are the end connectors.
    """
    length = min(polyline_length(points1), polyline_length(points2))
    segments = int(round(length / STITCH_LINE_STEP_MM))
    segments = max(1, min(STITCH_LINE_SEGMENTS_MAX, segments))
    fractions = np.linspace(0.0, 1.0, segments + 1)
    sampled1 = sample_polyline(points1, fractions)
    sampled2 = sample_polyline(points2, fractions)
    positions = []
    for point1, point2 in zip(sampled1, sampled2):
        positions.append(pattern1.pattern_to_view_pos(point1))
        positions.append(pattern2.pattern_to_view_pos(point2))
    return positions


class SewingRenderer(BaseRenderer):
    identity_attribute = "sewing_uuid"

    def __init__(self, sewing):
        super().__init__()
        self.batch_edge1 = None
        self.batch_edge2 = None
        self.batch_stitch_lines = None
        self.sewing_uuid = sewing.global_uuid

    @property
    def sewing(self):
        return global_data.get_obj_by_uuid(self.sewing_uuid, False)

    def ensure_batch(self) -> bool:
        """Whether the batches this renderer draws with are there.

        A seam whose batch was never built - the renderer is made before the two
        halves are walked, and a half the walk refuses leaves it without points -
        has to ask the seam to build again, and then say so if it still cannot.
        Drawing a batch that is not there raises inside the draw callback on
        every frame, which is what takes the editor's own drawing down with it.
        """
        if self.batch_edge1 is not None:
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
        return self.batch_edge1 is not None

    def update_batch_edge(self, render_points1, render_points2):
        # console.info('update_batch_edge')
        # console.info(render_points1, render_points1.flags['C_CONTIGUOUS'])
        # console.info(render_points2, render_points2.flags['C_CONTIGUOUS'])
        self.batch_edge1 = batch_for_shader(
            self.shader, 'LINE_STRIP',
            {"pos": render_points1},
        )
        self.batch_edge2 = batch_for_shader(
            self.shader, 'LINE_STRIP',
            {"pos": render_points2},
        )
        p1 = self.sewing.pattern1
        p2 = self.sewing.pattern2
        if p1 is None or p2 is None:
            # A seam whose pattern is gone has nothing to draw; the seam is what
            # the editor drops, this only keeps the frame alive until it does.
            return
        # Both halves are drawn as their polylines whatever their direction:
        # calc_sewing_side_render_points normalises the sampling order, so the
        # drawn polyline cannot carry the direction. The correspondence is
        # shown only by the connectors below, from the sample order, which is
        # the order the halves were created in.
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
        self.batch_edge1.draw(self.shader)

        transform_matrix = p2.calc_matrix()
        self.update_model_matrix(transform_matrix)
        self.batch_edge2.draw(self.shader)

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
        self.batch_edge1.draw(self.shader)

        p2 = sewing.pattern2
        if p2 is None:
            return
        transform_matrix = p2.calc_matrix()
        self.update_model_matrix(transform_matrix)
        self.shader.uniform_float("color", manager.index_to_rgb(
            sewing.side2.global_uuid if side2_id is None else side2_id))
        self.batch_edge2.draw(self.shader)
