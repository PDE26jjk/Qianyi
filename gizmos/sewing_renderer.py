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
from utilities.console import console_print, console
from utilities.coords_transform import create_2d_matrix


class SewingRenderer(BaseRenderer):

    def __init__(self, sewing):
        super().__init__()
        self.batch_edge1 = None
        self.batch_edge2 = None
        self.batch_dashed_line = None
        self.sewing_uuid = sewing.global_uuid

    @property
    def sewing(self):
        return global_data.get_obj_by_uuid(self.sewing_uuid)

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
        p1 = self.sewing.side1.line1.pattern
        p2 = self.sewing.side2.line1.pattern
        lines = [p1.pattern_to_view_pos(render_points1[0]), p2.pattern_to_view_pos(render_points2[0]),
                 p1.pattern_to_view_pos(render_points1[-1]), p2.pattern_to_view_pos(render_points2[-1])]
        # TODO dashed line shader
        self.batch_dashed_line = batch_for_shader(
            self.shader, 'LINES',
            {"pos": lines},
        )

    def draw(self, dashed_line=False):
        if not self.shader:
            return
        if self.batch_edge1 is None:
            self.sewing.need_update_points = True
            self.sewing.update()
        gpu.state.blend_set('ALPHA')
        self.shader.bind()
        self.shader.uniform_float("color", (*self.sewing.color, 1))
        p1 = self.sewing.side1.line1.pattern
        p2 = self.sewing.side2.line1.pattern
        transform_matrix = p1.calc_matrix()
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.batch_edge1.draw(self.shader)

        transform_matrix = p2.calc_matrix()
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.batch_edge2.draw(self.shader)

        if dashed_line:
            self.shader.uniform_float("ModelMatrix", Matrix.Identity(4))
            self.batch_dashed_line.draw(self.shader)

    def draw_id(self):
        if not self.shader:
            return
        sewing = self.sewing
        if self.batch_edge1 is None:
            sewing.need_update_points = True
            sewing.update()

        gpu.state.depth_test_set('NONE')

        self.shader.bind()
        p1 = self.sewing.side1.line1.pattern
        transform_matrix = p1.calc_matrix()
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("color", global_data.temp_draw_manager.index_to_rgb(sewing.side1.global_uuid))
        self.batch_edge1.draw(self.shader)

        p2 = self.sewing.side2.line1.pattern
        transform_matrix = p2.calc_matrix()
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("color", global_data.temp_draw_manager.index_to_rgb(sewing.side2.global_uuid))
        self.batch_edge2.draw(self.shader)
