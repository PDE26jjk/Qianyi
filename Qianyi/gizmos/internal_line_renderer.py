import math

import bpy
import gpu
import mathutils
import numpy as np
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from .base_renderer import BaseRenderer
from .. import global_data
from ..model.model_data import owner_pattern

from ..utilities.coords_transform import create_2d_matrix, create_2d_matrix_invert


class InternalLineRenderer(BaseRenderer):
    identity_attribute = "line_uuid"

    def __init__(self, line):
        super().__init__()
        self.batch_edge = None
        self.batch_vertex = None
        self.batch_spline_point = None
        self.line_uuid = line.global_uuid

    @property
    def pattern(self):
        """The pattern that owns the Sketch the line lives in, or None."""
        return owner_pattern(self.line)

    @property
    def line(self):
        return global_data.get_obj_by_uuid(self.line_uuid, False)

    def update_batch_edge(self, render_points):
        self.batch_edge = batch_for_shader(
            self.shader, 'LINE_LOOP' if self.line.is_loop else 'LINE_STRIP',
            {"pos": render_points},
        )

    def update_batch_spline_point(self, spline_points):
        self.batch_spline_point = batch_for_shader(
            self.shader, 'POINTS',
            {"pos": spline_points},
        )

    def draw_edges(self, color=(1.0, 1.0, 1.0, 0.5), pattern=None):
        """Draw this line for one pattern; `pattern` is the member to draw it in."""
        if not self.batch_edge:
            self.update_batch_edge(self.pattern.render_points)
        if pattern is None:
            pattern = self.pattern
        if not pattern:
            return
        # self.pattern.update_render_points()
        # 设置GPU状态
        gpu.state.blend_set('ALPHA')
        # gpu.state.depth_test_set('NONE')

        self.shader.bind()
        transform_matrix = pattern.calc_matrix()

        # self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.update_model_matrix(transform_matrix)
        self.shader.uniform_float("color", color)
        self.batch_edge.draw(self.shader)

    # def draw_instance_edges(self, anchor, rotation, mirror=False, scale=(1, 1),
    #                         color=(1.0, 1.0, 1.0, 0.7), thickness=2.0):
    #
    #     if not self.batch_edge:
    #         self.update_batch_edge(self.pattern.render_points)
    #
    #     gpu.state.blend_set('ALPHA')
    #     gpu.state.line_width_set(thickness)
    #     self.shader.bind()
    #
    #     final_scale_x = scale[0] * (-1 if mirror else 1)
    #     final_scale_y = scale[1]
    #     model_mat = create_2d_matrix(scale=(final_scale_x, final_scale_y), rotation=rotation, offset=anchor)
    #     self.update_model_matrix(model_mat)
    #     self.shader.uniform_float("color", color)
    #     self.batch_edge.draw(self.shader)

    # def draw_vertices(self, color=(1.0, 1.0, 1.0, 0.5)):
    #     if not self.shader:
    #         return
    #     if not self.batch_vertex:
    #         self.pattern.update_render_vertex()
    #     if not self.batch_spline_point:
    #         self.pattern.update_render_spline_point()
    #
    #     gpu.state.blend_set('ALPHA')
    #
    #     self.shader.bind()
    #     transform_matrix = self.pattern.calc_matrix()
    #     self.update_model_matrix(transform_matrix)
    #     self.shader.uniform_float("color", color)
    #     self.batch_vertex.draw(self.shader)
    #
    #     self.shader.uniform_float("color", (1, 0.2, 0., 0.8))
    #     self.batch_spline_point.draw(self.shader)
