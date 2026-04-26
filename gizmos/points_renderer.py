
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from .base_renderer import BaseRenderer
from utilities.coords_transform import create_2d_matrix


class PointsRenderer(BaseRenderer):
    def __init__(self):
        super().__init__()
        self.batch = None
        self.points = []

    def add_point(self, pattern, point):
        transform_matrix = pattern.calc_matrix()
        if hasattr(point, 'position'):
            pos = transform_matrix @ Vector((point.position[0], point.position[1], 0, 1))
        else:
            pos = transform_matrix @ Vector((point[0], point[1], 0, 1))

        self.points.append(pos[:3])

    def create_batch(self):
        self.batch = batch_for_shader(
            self.shader, 'POINTS',
            {"pos": self.points},
        )

    def draw(self, color=(1, 1, 1, 1), point_size=1):
        if not self.points:
            return
        if self.batch is None:
            self.create_batch()
        gpu.state.blend_set('ALPHA')
        gpu.state.point_size_set(point_size)
        transform_matrix = Matrix.Identity(4)
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        self.shader.uniform_float("color", color)
        self.batch.draw(self.shader)

