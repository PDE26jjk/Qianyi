from typing import Any, List

import numpy as np
from bpy.props import FloatVectorProperty, CollectionProperty, EnumProperty, IntVectorProperty, \
    FloatProperty, PointerProperty, BoolProperty, IntProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
from rich import segment

from ..utilities.geometric_operation import resample_polyline
from ..utilities.cubic_spline import cubic_spline_2d_numpy
from .model_data import ModelData, define_temp_prop, Selectable

from .section import Section


class Vertex2D(PropertyGroup, ModelData, Selectable):
    """Vertex"""
    co: FloatVectorProperty(
        name="coordinates",
        description="The coordinates of the point",
        subtype="XYZ",
        size=2,
        unit="LENGTH",
        # update=tag_update,
    )

    @property
    def position(self):
        return np.asarray(self.co)

    @position.setter
    def position(self, value):
        self.co[0] = value[0]
        self.co[1] = value[1]

    def clear_temp_data(self):
        self.pattern = None


define_temp_prop(Vertex2D, "pattern", None)

EdgeType = [
    ("BESSEL", "Bessel", "", 1),
    ("CUBIC_SPLINE", "points", "", 2),  # cubic spline
]

HandleType = [
    ("ALIGNED", "Aligned", "Aligned handles", 0, 1),
    ("VECTOR", "Vector", "Vector handles", 0, 2),
    ("FREE", "Free", "Free handles", 0, 4),
]


class Edge2D(PropertyGroup, ModelData, Selectable):
    type: EnumProperty(name="edgeType", items=EdgeType, default="BESSEL")
    vertex_index: IntVectorProperty(name="vertexIndex", size=2, default=(0, 0))
    handle1_pos: FloatVectorProperty(name="handle1Pos", size=2, default=(0.0, 0.0))
    handle2_pos: FloatVectorProperty(name="handle2Pos", size=2, default=(0.0, 0.0))
    handle1_type: EnumProperty(name="handle1Type", items=HandleType, default="VECTOR")
    handle2_type: EnumProperty(name="handle2Type", items=HandleType, default="VECTOR")
    geo_points: CollectionProperty(name="geoPoints", type=Vertex2D, )
    spline_points: CollectionProperty(name="splinePoints", type=Vertex2D, )
    bbox: FloatVectorProperty(name="bBox", size=4, default=(0, 0, 1, 1))

    def initialize(self):
        if len(self.geo_points) > 0:
            pts = []
            for point in self.geo_points:
                pts.append(point.co)
            self.geo_points_temp = np.asarray(pts)

    def reverse(self):
        self.vertex_index[0], self.vertex_index[1] = self.vertex_index[1], self.vertex_index[0]
        self.handle1_pos, self.handle2_pos = self.handle2_pos[:], self.handle1_pos[:]
        self.handle1_type, self.handle2_type = self.handle2_type, self.handle1_type

    def update(self, pattern=None):
        if not self.need_update_points:
            return
        if pattern is not None:
            self.pattern = pattern
        self.vertices[0] = self.pattern.vertices[self.vertex_index[0]].co[:]
        self.vertices[1] = self.pattern.vertices[self.vertex_index[1]].co[:]
        self.render_points = self.generate_render_points()
        self.calc_length()
        # self.sections.clear()
        # self.sections.append(Section(0., self))
        # self.sections[0].length = self.length

        self.calc_geo_point_for_sections()
        self.geo_points.clear()
        self.calc_bbox(self.geo_points_temp)

        for i in range(self.geo_points_temp.shape[0]):
            p = self.geo_points.add()
            p.co = self.geo_points_temp[i]
        self.need_update_points = False

    def calc_bbox(self, points):
        bbox_min = points.min(axis=0)
        bbox_max = points.max(axis=0)
        # bpy.context.workspace.status_text_set(f"{self.geo_points_temp.min(axis=0)} {self.geo_points_temp.max(axis=0)}")
        self.bbox[0] = bbox_min[0]
        self.bbox[1] = bbox_min[1]
        self.bbox[2] = bbox_max[0]
        self.bbox[3] = bbox_max[1]

    def calc_length(self):
        if self.type == "BESSEL":
            # bpy.context.workspace.status_text_set(f"{self.handle1_type} {self.handle2_type}")
            if self.handle1_type == "VECTOR" and self.handle2_type == "VECTOR":
                self.length = np.linalg.norm(np.asarray(self.vertices[0]) - np.asarray(self.vertices[1]))
                return

            q = np.array([self.vertices[0], self.handle1_pos, self.handle2_pos, self.vertices[1]])
            pts = self.forward_diff_bezier(q, 1000)
            self.length = np.sum(np.linalg.norm(pts[1:] - pts[:-1], axis=1))
        elif self.type == "CUBIC_SPLINE":
            edge_points = [p.co for p in self.spline_points]
            q = np.array((self.vertices[0], *edge_points, self.vertices[1]))
            # point_count = q.shape[0]
            # t = np.linspace(0, point_count, point_count)
            t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
            pts = cubic_spline_2d_numpy(t, q, sample_count=1000)
            self.length = np.sum(np.linalg.norm(pts[1:] - pts[:-1], axis=1))

    @staticmethod
    def forward_diff_bezier(q, n):
        """
        计算单条2D贝塞尔曲线的离散点（完全向量化实现）

        参数:
            q: (4, 2) 形状的数组，包含曲线的控制点
            n: 迭代次数（分段数）

        返回:
            points: (n+1, 2) 形状的数组，曲线上的点
        """
        assert q.shape == (4, 2), f"Expected control points shape (4,2), got {q.shape}"
        if n == 0:
            return np.array([q[0]])

        # 计算差分变量
        rt0 = q[0]
        rt1 = 3.0 * (q[1] - q[0]) / n
        rt2 = 3.0 * (q[0] - 2.0 * q[1] + q[2]) / (n * n)
        rt3 = (q[3] - q[0] + 3.0 * (q[1] - q[2])) / (n * n * n)

        # 重组迭代变量
        q0 = rt0
        q1 = rt1 + rt2 + rt3
        q2 = 2 * rt2 + 6 * rt3
        q3 = 6 * rt3

        # 创建索引数组
        k = np.arange(n + 1)

        # 使用累加和公式计算点位置
        term1 = k[:, None] * q1
        term2 = (k * (k - 1) / 2)[:, None] * q2
        term3 = (k * (k - 1) * (k - 2) / 6)[:, None] * q3

        return q0 + term1 + term2 + term3

    def add_edge_point(self, position):
        point = self.spline_points.add()
        point.co = position
        return point

    def generate_render_points(self, render_point_count=1024):
        if self.type == "BESSEL":
            if self.handle1_type == "VECTOR" and self.handle2_type == "VECTOR":
                return np.array((self.vertices[0], self.vertices[1]))
            q = np.array([self.vertices[0], self.handle1_pos, self.handle2_pos, self.vertices[1]])
            return self.forward_diff_bezier(q, render_point_count)
        elif self.type == "CUBIC_SPLINE":
            edge_points = [p.co for p in self.spline_points]
            q = np.array((self.vertices[0], *edge_points, self.vertices[1]))
            # point_count = q.shape[0]
            # t = np.linspace(0, point_count, point_count)
            t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
            res = cubic_spline_2d_numpy(t, q, sample_count=render_point_count)
            # TODO utilize handles
            return res

        return np.array((self.vertices[0], self.vertices[1]))

    def sections(self):
        max_sec = 10000
        sec: Section = self.section_start
        if sec is None:
            self.pattern.create_sections()
            sec = self.section_start
        assert sec is not None, "Sections are not created!!!"
        while sec is not self.section_end and max_sec > 0:
            yield sec
            sec = sec.next
            max_sec -= 1
        if max_sec == 0:
            raise ValueError("Wrong section link!!")

    def calc_temp_geo_point(self, resolution):
        # if self.type == "BESSEL":
        #     if self.handle1_type == "VECTOR" and self.handle2_type == "VECTOR":
        #         self.geo_points_temp = np.linspace(self.vertices[0], self.vertices[1], resolution)
        #         return
        # points = np.asarray(self.render_points)
        # arc_points = []
        # cumulative_lengths = np.insert(np.cumsum(np.linalg.norm(points[1:] - points[:-1], axis=1)), 0, 0)
        # target_lengths = np.linspace(0, self.length, resolution)
        # j = 0  # 当前点索引
        # for target in target_lengths:
        #     # 找到包含目标弧长的线段
        #     while j < len(cumulative_lengths) - 1 and cumulative_lengths[j + 1] < target:
        #         j += 1
        #
        #     if j >= len(cumulative_lengths) - 1:
        #         arc_points.append(points[-1].copy())
        #     else:
        #         # 计算在线段中的位置
        #         L0 = cumulative_lengths[j]
        #         L1 = cumulative_lengths[j + 1]
        #         t = (target - L0) / (L1 - L0) if L1 > L0 else 0.0
        #
        #         # 线性插值
        #         p0 = points[j]
        #         p1 = points[j + 1]
        #         interpolated = p1 * t + p0 * (1 - t)
        #         arc_points.append(interpolated)

        # q = np.array([self.vertices[0], self.handle1_pos, self.handle2_pos, self.vertices[1]])
        # self.geo_points_temp = self.forward_diff_bezier(q, resolution)
        # self.geo_points_temp = np.asarray(mathutils.geometry.interpolate_bezier(*q, resolution))
        # self.geo_points_temp = np.asarray(arc_points)
        segment = max(resolution - 1, 1)
        temp_points = self.generate_render_points(segment * 2)
        self.geo_points_temp = resample_polyline(temp_points, [(0, segment)], True)

    def calc_geo_point_for_sections(self):
        min_g = self.pattern.granularity
        for sec in self.sections():
            if sec.seg == -1:
                sec.seg = max(round(sec.absolute_length() / sec.edge.pattern.granularity), 1)
            min_g = min(sec.absolute_length() / sec.seg, min_g)
        resolution = max(round(self.length / min_g), 1) + 1
        only_one_section = self.section_start.next == self.section_end
        if only_one_section:
            self.calc_temp_geo_point(resolution)
            self.section_start.start_point = 0
        else:
            self.calc_temp_geo_point(resolution * 2)
            segments = []
            points_count = 0
            for sec in self.sections():
                sec.start_point = points_count
                points_count += sec.seg
                segments.append((sec.start_pos,sec.seg))
            self.geo_points_temp = resample_polyline(self.geo_points_temp, segments,True)
        return

    def clear_temp_data(self):
        self.pattern = None
        self.need_update_points = True

    def find_section_index(self, pos):
        for i, sec in enumerate(self.sections):  # TODO dichotomy
            if pos >= sec.start_pos:
                eps = 1e-4
                if pos - sec.start_pos < eps:
                    return i

    def find_or_add_section(self, pos) -> Section | None:
        eps = 1e-5
        if pos >= 1 - eps:
            return self.section_end
        max_sec = 10000
        sec: Section = self.section_start
        while sec is not self.section_end and max_sec > 0:
            if pos >= sec.start_pos:
                if pos - sec.start_pos < eps:
                    return sec
                radio = (pos - sec.start_pos) / (sec.end_pos - sec.start_pos)
                _, new_sec = sec.split(radio)
                return new_sec
            sec = sec.next
            max_sec -= 1
        if max_sec == 0:
            raise ValueError("Wrong section link!!")
        return None
        # self.sections: List[Section]
        # for i, sec in enumerate(self.sections):  # TODO dichotomy
        #     if pos >= sec.start_pos:
        #         eps = 1e-4
        #         if pos - sec.start_pos < eps:
        #             return sec
        #         if i < len(self.sections) - 1:
        #             if self.sections[i + 1].start_pos - pos < eps:
        #                 return self.sections[i + 1]
        #         if i == len(self.sections) - 1 and pos > 1 - eps:
        #             return None
        #         new_section = Section(pos, self)
        #         next_pos = 1. if i == len(self.sections) - 1 else self.sections[i + 1].start_pos
        #         ratio = (pos - sec.start_pos) / (next_pos - sec.start_pos)
        #         new_length = sec.length * ratio
        #         new_section.length = sec.length - new_length
        #         sec.length = new_length
        #         self.sections.insert(i + 1, new_section)
        #         if sec.link_map_id != -1:
        #             sections_to_insert = []
        #             sections_to_insert.extend(Section.link_sections[sec.link_map_id])
        #             sections_to_insert.remove(sec)
        #             sections_to_link = [new_section]
        #             link_index = len(Section.link_sections)
        #             for link_sec in sections_to_insert:
        #                 index = link_sec.edge.find_section_index(link_sec.start_pos)
        #                 sections = link_sec.edge.sections
        #                 next_pos = 1. if index == len(sections) - 1 else sections[index + 1].start_pos
        #                 new_pos = link_sec.start_pos + (next_pos - link_sec.start_pos) * ratio
        #                 new_length = link_sec.length * ratio
        #                 _new_section = Section(new_pos, link_sec.edge)
        #                 _new_section.length = link_sec.length - new_length
        #                 _new_section.link_map_id = link_index
        #                 link_sec.length = new_length
        #                 sections.insert(index + 1, _new_section)
        #                 sections_to_link.append(_new_section)
        #             Section.link_sections.append(sections_to_link)
        #
        #         return new_section
        #


define_temp_prop(Edge2D, "pattern", None)
define_temp_prop(Edge2D, "length", None)
define_temp_prop(Edge2D, "vertices", lambda: [(0.0, 0.0), (0.0, 0.0)])
define_temp_prop(Edge2D, "need_update_points", True)
define_temp_prop(Edge2D, "render_points", None)
define_temp_prop(Edge2D, "geo_points_temp", None)
define_temp_prop(Edge2D, "section_start", None)
define_temp_prop(Edge2D, "section_end", None)
define_temp_prop(Edge2D, "start_point", -1)

register, unregister = register_classes_factory((Vertex2D, Edge2D,))
