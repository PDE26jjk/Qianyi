import math

import bpy
import gpu
import mathutils
import numpy as np
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from utilities.console import console_print
from utilities.coords_transform import create_2d_matrix

# 自定义着色器代码
vertex_shader = '''
uniform mat4 ModelMatrix;
uniform mat4 ViewProjectionMatrix;

in vec2 pos;

void main()
{
    gl_Position = ViewProjectionMatrix * ModelMatrix * vec4(pos, 0.0, 1.0); 
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


class SewingRenderer:
    shader = None

    def __init__(self, sewing):
        self.draw_handle = None
        self.batch_edge1 = None
        self.batch_edge2 = None
        self.sewing = sewing
        if self.shader is None:
            self.shader = GPUShader(vertex_shader, fragment_shader)

    def update_batch_edge(self, render_points1, render_points2):
        self.batch_edge1 = batch_for_shader(
            self.shader, 'LINE_STRIP',
            {"pos": render_points1},
        )
        self.batch_edge2 = batch_for_shader(
            self.shader, 'LINE_STRIP',
            {"pos": render_points2},
        )
        # console_print(render_points1)
        # bpy.context.workspace.status_text_set(render_points[0])

    def draw(self, region_matrix, ):
        if not self.shader:
            return
        gpu.state.blend_set('ALPHA')
        # gpu.state.depth_test_set('NONE')
        if self.batch_edge1 is None:
            self.sewing.need_update_points = True
            self.sewing.update()

        self.shader.bind()
        p1 = self.sewing.side1.line1.pattern
        p2 = self.sewing.side2.line1.pattern
        scale = 0.001 * 1.539
        transform_matrix = create_2d_matrix(rotation=p1.rotation, offset=p1.anchor)
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("ViewProjectionMatrix", region_matrix @ create_2d_matrix(scale=(scale, scale)))
        self.shader.uniform_float("color", (*self.sewing.color,1))
        self.batch_edge1.draw(self.shader)

        transform_matrix = create_2d_matrix(rotation=p2.rotation, offset=p2.anchor)
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.batch_edge2.draw(self.shader)
