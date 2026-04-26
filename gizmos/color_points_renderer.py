import gpu
from gpu.types import GPUShader
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from .points_renderer import PointsRenderer

# ---------- 新的着色器：支持逐顶点颜色 ----------
vertex_shader_multicolor = '''
uniform mat4 ModelMatrix;
uniform mat4 ModelViewProjectionMatrix;
in vec2 pos;
in vec4 color;          
out vec4 vColor;        
void main()
{
    gl_Position = ModelViewProjectionMatrix * ModelMatrix * vec4(pos, 0.0, 1.0);
    vColor = color;
}
'''
fragment_shader_multicolor = '''
in vec4 vColor;   
out vec4 fragColor;
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
            self.shader = GPUShader(
                vertex_shader_multicolor,
                fragment_shader_multicolor
            )

    def add_point(self, pattern, point, color=(1, 1, 1, 1)):
        transform_matrix = pattern.transform_mat_2D
        if hasattr(point, 'position'):
            pos = transform_matrix @ Vector((point.position[0], point.position[1], 0, 1))
        else:
            pos = transform_matrix @ Vector((point[0], point[1], 0, 1))
        self.points.append(pos[:3])
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
        transform_matrix = Matrix.Identity(4)
        self.shader.uniform_float("ModelMatrix", transform_matrix)

        self.batch.draw(self.shader)
