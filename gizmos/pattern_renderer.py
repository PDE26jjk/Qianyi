import math

import bpy
import gpu
import mathutils
import numpy as np
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from .. import global_data

from utilities.coords_transform import create_2d_matrix

# 自定义着色器代码
vertex_shader = '''
uniform mat4 ModelMatrix;
uniform mat4 ViewProjectionMatrix;

in vec2 pos;

void main()
{
    gl_Position = ViewProjectionMatrix * ModelMatrix * vec4(pos, 0.0, 1.0); // why?
    // gl_Position.w /= 2; 
}
'''

fragment_shader = '''
uniform vec4 color;

out vec4 fragColor;

void main()
{
    fragColor = color;
}
'''


class PatternRenderer:
    shader = None

    def __init__(self, pattern):
        self.draw_handle = None
        self.batch_edge = None
        self.batch_vertex = None
        self.pattern_uuid = pattern.global_uuid
        if self.shader is None:
            self.shader = GPUShader(vertex_shader, fragment_shader)

    @property
    def pattern(self):
        return global_data.get_obj_by_uuid(self.pattern_uuid)

    def update_batch_edge(self, render_points):
        # 创建批次
        self.batch_edge = batch_for_shader(
            self.shader, 'LINE_LOOP',
            {"pos": render_points},
        )
        # bpy.context.workspace.status_text_set(render_points[0])

    def update_batch_vertex(self, vertex_points):
        # 创建批次
        self.batch_vertex = batch_for_shader(
            self.shader, 'POINTS',
            {"pos": vertex_points},
        )

    def draw_edges(self, region_matrix, color=(1.0, 1.0, 1.0, 0.5)):
        if not self.shader:
            return
        if not self.batch_edge:
            self.update_batch_edge(self.pattern.render_points)
        # self.pattern.update_render_points()
        # 设置GPU状态
        gpu.state.blend_set('ALPHA')
        # gpu.state.depth_test_set('NONE')

        self.shader.bind()
        transform_matrix = create_2d_matrix(rotation=self.pattern.rotation,
                                            offset=self.pattern.anchor)

        scale = 0.001 * 1.539
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("ViewProjectionMatrix", region_matrix @ create_2d_matrix(scale=(scale, scale)))
        self.shader.uniform_float("color", color)
        self.batch_edge.draw(self.shader)

    def draw_vertices(self, region_matrix, color=(1.0, 1.0, 1.0, 0.5)):
        if not self.shader:
            return
        if not self.batch_vertex:
            self.pattern.update_render_vertex()

        gpu.state.blend_set('ALPHA')

        self.shader.bind()
        transform_matrix = create_2d_matrix(rotation=self.pattern.rotation,
                                            offset=self.pattern.anchor)
        scale = 0.001 * 1.539
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("ViewProjectionMatrix", region_matrix @ create_2d_matrix(scale=(scale, scale)))
        self.shader.uniform_float("color", color)
        self.batch_vertex.draw(self.shader)
