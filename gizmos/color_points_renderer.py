import gpu
from gpu.types import GPUShaderCreateInfo
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from .points_renderer import PointsRenderer

# ---------- 着色器源码：只写 main() 函数体，不再声明 uniform/in/out ----------
vertex_shader_multicolor = '''
void main()
{
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0);
    vColor = color;
}
'''
fragment_shader_multicolor = '''
void main()
{
    fragColor = vColor;
}
'''


class MultiColorPointsRenderer:
    shader = None

    def __init__(self):
        self.batch = None
        self.points = []
        self.colors = []
        if self.shader is None:
            # ===== 使用新的 GPUShaderInfo API =====
            shader_info = GPUShaderCreateInfo()
            # 顶点输入
            shader_info.vertex_in(0, 'VEC2', 'pos')
            shader_info.vertex_in(1, 'VEC4', 'color')
            # 顶点 -> 片段 的 varying
            interface = gpu.types.GPUStageInterfaceInfo("MyInterface")
            interface.flat('VEC4', 'vColor')  # smooth 表示平滑插值（默认），如果是整数颜色可以用 flat
            shader_info.vertex_out(interface)

            # 片段输出
            shader_info.fragment_out(0, 'VEC4', 'fragColor')
            # Uniform（在新 API 中叫 push_constant）
            shader_info.push_constant('MAT4', 'ModelViewProjectionMatrix')
            # 着色器源码（只有 main 函数体）
            shader_info.vertex_source(vertex_shader_multicolor)
            shader_info.fragment_source(fragment_shader_multicolor)
            # 创建着色器
            self.shader = gpu.shader.create_from_info(shader_info)

    def add_point(self, pattern, point, color=(1, 1, 1, 1)):
        transform_matrix = pattern.transform_mat_2D
        if hasattr(point, 'position'):
            pos = transform_matrix @ Vector((point.position[0], point.position[1], 0, 1))
        else:
            pos = transform_matrix @ Vector((point[0], point[1], 0, 1))
        # ⚠️ 着色器声明的是 VEC2，所以只取前两个分量
        self.points.append((pos[0], pos[1]))
        self.colors.append(color)

    def create_batch(self):
        self.batch = batch_for_shader(
            self.shader, 'POINTS',
            {
                "pos": self.points,
                "color": self.colors,
            },
        )

    def draw(self, point_size=1, draw_id=False):
        if not self.points:
            return
        if self.batch is None:
            self.create_batch()
        if draw_id:
            gpu.state.blend_set('NONE')
        else:
            gpu.state.blend_set('ALPHA')
        gpu.state.point_size_set(point_size)
        self.batch.draw(self.shader)