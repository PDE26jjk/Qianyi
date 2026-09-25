from typing import List

import bpy
import numpy as np
from mathutils import Matrix, Vector

from ..model.geometry import Vertex2D, Edge2D
from ..model.model_data import owner_pattern
from ..utilities.cubic_spline import cubic_spline_2d_numpy
from ..utilities.geometric_operation import forward_diff_bezier, generate_curve_points
from .. import global_data


class TempPoint:
    def __init__(self, co):
        self.co = co


class ProxyPoint:
    def __init__(self, vertex):
        self.vertex = vertex
        self.co = vertex.co[:]
        vertex.proxy = self

    def update_offset(self, offset, pattern=None):
        """Move this point by a pointer offset, in the space of `pattern`.

        The offset comes from the pointer and therefore moves in view space; the
        point lives in the pattern space of the pattern the pointer is over. That
        pattern is what the offset is converted with - its own inverse transform
        carries its mirror and its rotation - because the pattern that owns the
        Sketch is the first member of the chain, which need not be the one being
        dragged: converting through the owner moves a mirrored instance's point
        the other way along the mouse.
        """
        if pattern is None:
            pattern = owner_pattern(self.vertex)
        if pattern is None:
            raise ValueError("this point has no pattern to move in: the Sketch it "
                             "lives in names no owner")
        if pattern.inv_transform_mat_2D is None:
            pattern.calc_inv_matrix()
        offset_relative = pattern.inv_transform_mat_2D @ Vector((offset[0], offset[1], 0, 0))
        self.co = self.vertex.co + Vector((offset_relative[0], offset_relative[1]))

    def apply_proxy(self):
        """Write this point's new place into the Sketch it lives in.

        One Sketch serves the whole instance chain, so there is nothing per
        member to write: this is the one point, and every member draws it from
        where it now is.
        """
        self.vertex.co = self.co[:]


def get_proxy_or_not(vertex) -> ProxyPoint | Vertex2D:
    return vertex.proxy if vertex.proxy is not None else vertex


class MovingCurve:
    def __init__(self, edge: Edge2D = None):
        if edge:
            self.edge_uuid = edge.global_uuid
            self.handle1_type = edge.handle1_type
            self.handle2_type = edge.handle2_type
            self.vertex0 = get_proxy_or_not(edge.vertex0)
            self.vertex1 = get_proxy_or_not(edge.vertex1)
            self.handle1 = get_proxy_or_not(edge.handle1)
            self.handle2 = get_proxy_or_not(edge.handle2)
            self.spline_points = [get_proxy_or_not(v) for v in edge.spline_points]
        else:
            self.edge_uuid = -1
            self.handle1_type = self.handle2_type = "VECTOR"
            self.vertex0 = TempPoint((0., 0))
            self.vertex1 = TempPoint((0., 0))
            self.handle1 = TempPoint((0., 0))
            self.handle2 = TempPoint((0., 0))
            self.spline_points = []
        from .curve_renderer import MovingCurveRenderer
        self.render_points = np.array([])
        self.renderer = MovingCurveRenderer(self)

    @property
    def edge(self):
        return global_data.get_obj_by_uuid(self.edge_uuid)

    def generate_render_points(self, render_point_count=1024):
        h1 = None if self.handle1_type == "VECTOR" else self.handle1.co
        h2 = None if self.handle2_type == "VECTOR" else self.handle2.co
        v0 = self.vertex0.co
        v1 = self.vertex1.co
        edge_points = [p.co for p in self.spline_points]
        q = np.array((v0, *edge_points, v1))
        return generate_curve_points(q, h1, h2, render_point_count).astype(np.float32)

    def update(self):
        self.render_points = self.generate_render_points(render_point_count=1024)
        self.renderer.update_batch()

    def apply_moving(self):
        pass  # done by proxy points


def move_points_with_segment(points, v0, v1, new_v0, new_v1):
    """
    点集随线段移动，保持点到线段的垂直距离和投影比例不变
    """
    u_x, u_y = v1[0] - v0[0], v1[1] - v0[1]
    nu_x, nu_y = new_v1[0] - new_v0[0], new_v1[1] - new_v0[1]

    L2 = u_x * u_x + u_y * u_y
    L = np.sqrt(L2)
    L_new = np.sqrt(nu_x * nu_x + nu_y * nu_y)

    if L == 0 or L_new == 0:
        return points.copy()

    n_x, n_y = -u_y / L, u_x / L
    nn_x, nn_y = -nu_y / L_new, nu_x / L_new

    dp_x = points[:, 0] - v0[0]
    dp_y = points[:, 1] - v0[1]

    t = (dp_x * u_x + dp_y * u_y) / L2
    d = dp_x * n_x + dp_y * n_y

    new_points = np.empty_like(points, dtype=np.float64)
    new_points[:, 0] = new_v0[0] + t * nu_x + d * nn_x
    new_points[:, 1] = new_v0[1] + t * nu_y + d * nn_y

    return new_points


class MovingCurveWhole(MovingCurve):
    def __init__(self, edge: Edge2D):
        whole_points = np.array([edge.handle1, edge.handle2, *[p for p in edge.spline_points]])
        for p in whole_points:
            p.proxy = ProxyPoint(p)
        super().__init__(edge)
        self.whole_points: List[ProxyPoint] = [self.handle1, self.handle2, *[p for p in self.spline_points]]
        self.whole_points_pos = np.array([p.co for p in self.whole_points])

    def update(self):
        v0 = self.vertex0.co
        v1 = self.vertex1.co
        if isinstance(self.vertex0, ProxyPoint):
            v0 = self.vertex0.vertex.co
        if isinstance(self.vertex1, ProxyPoint):
            v1 = self.vertex1.vertex.co
        new_pos = move_points_with_segment(self.whole_points_pos, v0,
                                           v1, self.vertex0.co, self.vertex1.co)
        for i, p in enumerate(self.whole_points):
            p.co = new_pos[i]
        MovingCurve.update(self)

    def apply_moving(self):
        for point in self.whole_points:
            point.apply_proxy()
