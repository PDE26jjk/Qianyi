import math
import bpy
import gpu
import numpy as np
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from utilities.console import console
from .. import global_data
from utilities.coords_transform import create_2d_matrix

# 自定义着色器代码
vertex_shader = '''
 uniform mat4 ModelMatrix;
uniform mat4 ModelViewProjectionMatrix; // Set by blender

in vec2 pos;

void main()
{
    gl_Position = ModelViewProjectionMatrix * ModelMatrix * vec4(pos, 0.0, 1.0);
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


class CurveRenderer:
    shader = None

    def __init__(self, edge):
        self.batch = None
        self.edge_uuid = edge.global_uuid
        if self.shader is None:
            self.shader = GPUShader(vertex_shader, fragment_shader)

        self.update_batch()

    @property
    def edge(self):
        return global_data.get_obj_by_uuid(self.edge_uuid)

    def update_batch(self):
        if not self.edge or not hasattr(self.edge, 'render_points'):
            return

        render_points = self.edge.render_points
        self.batch = batch_for_shader(
            self.shader, 'LINE_STRIP',
            {"pos": render_points.astype(dtype=np.float32)},
        )

    def draw(self, color=(1.0, 1.0, 1.0, 0.5), thickness=1.0):
        """
        Args:
            color: 颜色 (R, G, B, A)
            thickness: 线宽
        """
        if not self.batch:
            self.update_batch()
            # return

        # 获取变换参数
        pattern = self.edge.pattern

        gpu.state.blend_set('ALPHA')
        # gpu.state.depth_test_set('NONE')
        gpu.state.line_width_set(thickness)
        self.shader.bind()

        transform_matrix = create_2d_matrix(rotation=pattern.rotation,
                                            offset=pattern.anchor)

        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("color", color)

        self.batch.draw(self.shader)


