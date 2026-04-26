import math
import bpy
import gpu
import numpy as np
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from utilities.console import console
from .base_renderer import BaseRenderer
from .moving_curve import MovingCurve
from .. import global_data
from utilities.coords_transform import create_2d_matrix


class CurveRenderer(BaseRenderer):
    def __init__(self, edge):
        super().__init__()
        self.batch = None
        self.handles_line_batch = None
        self.handle1_point_batch = None
        self.handle2_point_batch = None
        self.edge_uuid = edge.global_uuid
        if self.edge_uuid == -1:
            raise Exception(f"edge {edge} is invalid!")
        self.update_batch()

    @property
    def edge(self):
        e = global_data.get_obj_by_uuid(self.edge_uuid, True)
        if e is None:
            console.warning(f"edge {self.edge_uuid} not found")
        return e

    def update_batch(self):
        if not self.edge or not hasattr(self.edge, 'render_points'):
            return
        edge = self.edge
        render_points = edge.render_points
        self.batch = batch_for_shader(
            self.shader, 'LINE_STRIP',
            {"pos": render_points.astype(dtype=np.float32)},
        )
        self.handle1_point_batch = batch_for_shader(
            self.shader, 'POINTS',
            {"pos": [edge.handle1.co]},
        )
        self.handle2_point_batch = batch_for_shader(
            self.shader, 'POINTS',
            {"pos": [edge.handle2.co]},
        )
        lines = []
        if edge.handle1_type != "VECTOR":
            lines.extend((edge.vertex0.co, edge.handle1.co))
        if edge.handle2_type != "VECTOR":
            lines.extend((edge.vertex1.co, edge.handle2.co))

        self.handles_line_batch = batch_for_shader(
            self.shader, 'LINES',
            {"pos": lines},
        )

    def draw(self, color=(1.0, 1.0, 1.0, 0.5), thickness=1.0, draw_id=False):
        """
        Args:
            color: 颜色 (R, G, B, A)
            thickness: 线宽
            draw_id: draw_id
        """
        if not self.edge:
            return
        if not self.batch:
            self.update_batch()

        if draw_id:
            gpu.state.blend_set('NONE')
        else:
            gpu.state.blend_set('ALPHA')

        pattern = self.edge.pattern

        # gpu.state.depth_test_set('NONE')
        gpu.state.line_width_set(thickness)
        self.shader.bind()

        transform_matrix = pattern.calc_matrix()

        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("color", color)

        self.batch.draw(self.shader)

    def draw_instances(self, color=(1.0, 1.0, 1.0, 0.5), thickness=1.0):
        if not self.edge:
            return
        if not self.batch:
            self.update_batch()
        patterns = self.edge.pattern.instances
        if not patterns:
            return

        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(thickness)
        self.shader.bind()
        self.shader.uniform_float("color", color)

        for pattern in patterns:
            transform_matrix = pattern.calc_matrix()
            self.shader.uniform_float("ModelMatrix", transform_matrix)
            self.batch.draw(self.shader)

    def draw_handles(self, color=(1.0, 1.0, 1.0, 0.5), thickness=1.0, draw_id=False):
        if not self.edge:
            return
        if not self.batch:
            self.update_batch()

        if draw_id:
            gpu.state.blend_set('NONE')
        else:
            gpu.state.blend_set('ALPHA')

        edge = self.edge
        pattern = edge.pattern

        # gpu.state.depth_test_set('NONE')
        gpu.state.line_width_set(thickness)
        gpu.state.point_size_set(thickness * 2)
        self.shader.bind()

        transform_matrix = pattern.calc_matrix()

        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("color", color)
        if not draw_id:
            self.handles_line_batch.draw(self.shader)
        self.shader.uniform_float("color", (1, 1, 1, 1))
        if edge.handle1_type != "VECTOR":
            if draw_id:
                self.shader.uniform_float("color",
                                          global_data.temp_draw_manager.index_to_rgb(edge.handle1.global_uuid))
            self.handle1_point_batch.draw(self.shader)
        if edge.handle2_type != "VECTOR":
            if draw_id:
                self.shader.uniform_float("color",
                                          global_data.temp_draw_manager.index_to_rgb(edge.handle2.global_uuid))
            self.handle2_point_batch.draw(self.shader)


class MovingCurveRenderer(CurveRenderer):
    def __init__(self, moving_edge: MovingCurve):
        self.moving_edge = moving_edge
        super().__init__(moving_edge.edge)

    def update_batch(self):
        # console.warning("update_batch mc")
        render_points = self.moving_edge.render_points
        self.batch = batch_for_shader(
            self.shader, 'LINE_STRIP',
            {"pos": render_points.astype(dtype=np.float32)},
        )
