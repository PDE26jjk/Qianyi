import math

import bpy
import gpu
import mathutils
import numpy as np
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from .. import global_data
from ..utilities.coords_transform import create_2d_matrix

# 自定义着色器代码
vertex_shader = '''
uniform mat4 ModelMatrix;
uniform mat4 ModelViewProjectionMatrix; // Set by blender

in vec3 pos;

void main()
{
    gl_Position = ModelViewProjectionMatrix * ModelMatrix * vec4(pos.x,pos.y,0., 1.0);
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


class MeshRenderer:
    shader = None

    def __init__(self, pattern):
        self.pattern_uuid = pattern.global_uuid
        if self.shader is None:
            self.shader = GPUShader(vertex_shader, fragment_shader)
        self.batch_line = None
        self.batch_triangle = None
        self.obj = None

    @property
    def pattern(self):
        return global_data.get_obj_by_uuid(self.pattern_uuid)

    def create_batch(self, obj):
        """创建网格批次（只调用一次）"""
        if not obj or obj.type != 'MESH':
            return None

        mesh = obj.data

        # 确保 loop_triangles 数据是最新的 (通常很快)
        mesh.calc_loop_triangles()

        # --- 1. 获取顶点坐标 (Nx3) ---
        # 创建一个空的 numpy 数组，形状为 (顶点数, 3)
        vertices = np.empty((len(mesh.vertices), 3), dtype=np.float32)
        # 使用 foreach_get 直接将 C 内存数据复制到 numpy 数组中
        # .ravel() 将 2D 数组展平为 1D，因为 foreach_get 需要平铺的数据
        mesh.vertices.foreach_get("co", vertices.ravel())
        vertices *= 1000.
        # --- 2. 获取边索引 (Nx2) ---
        edges = np.empty((len(mesh.edges), 2), dtype=np.int32)
        mesh.edges.foreach_get("vertices", edges.ravel())

        # --- 3. 获取三角形索引 (Nx3) ---
        triangles = np.empty((len(mesh.loop_triangles), 3), dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles.ravel())

        if self.shader is None:
            self.setup_shader()

        # --- 4. 创建批次 ---
        # batch_for_shader 完美支持 numpy 数组作为输入，无需转回 Python List
        self.batch_line = batch_for_shader(
            self.shader, 'LINES',
            {"pos": vertices},  # numpy 数组直接传入
            indices=edges  # numpy 数组直接传入
        )

        self.batch_triangle = batch_for_shader(
            self.shader, 'TRIS',
            {"pos": vertices},  # 复用同一个顶点数据
            indices=triangles
        )

        return self.batch_line, self.batch_triangle

    def get_world_matrix(self):
        return create_2d_matrix(rotation=self.pattern.rotation,
                                offset=self.pattern.anchor)

    def draw_fill_mesh(self, color=(1.0, 1.0, 1.0, 0.5), draw_id=False):
        if not self.obj or not self.batch_triangle or not self.shader:
            return
        # 设置GPU状态
        if draw_id:
            gpu.state.blend_set('NONE')
        else:
            gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')

        self.shader.bind()

        self.shader.uniform_float("ModelMatrix", self.get_world_matrix())
        self.shader.uniform_float("color", color)
        self.batch_triangle.draw(self.shader)

    def draw_mesh_lines(self, selected=False):
        if not self.obj or not self.batch_line or not self.shader:
            return

        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')

        self.shader.bind()

        transform_matrix = create_2d_matrix(rotation=self.pattern.rotation,
                                            offset=self.pattern.anchor)
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        if selected:
            self.shader.uniform_float("color", (0.843, 0.596, 0.153, 1.0))
        else:
            self.shader.uniform_float("color", (1.0, 1.0, 1.0, 0.5))
        # 绘制批次
        gpu.state.line_width_set(1.0)
        self.batch_line.draw(self.shader)

    def start_rendering(self, obj):
        """开始渲染指定对象"""
        self.obj = None
        if not obj:
            return False

        self.batch_line, self.batch_triangle = self.create_batch(obj)

        if not self.batch_triangle:
            return False

        self.obj = obj
        return True
