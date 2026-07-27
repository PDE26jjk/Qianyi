import math
import re

import numpy as np
from bpy.props import FloatVectorProperty, CollectionProperty, EnumProperty, IntVectorProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .model_data import ModelData, define_temp_prop, Selectable
from .section import Section
from ..utilities.console import console
from ..utilities.geometric_operation import resample_polyline, generate_curve_points


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
        self.pattern_temp = None

    @property
    def pattern(self):
        if self.pattern_temp is not None:
            try:
                self.pattern_temp.path_from_id()
            except Exception as e:
                console.error("can not get pattern!", e)
                self.pattern_temp = None
        if self.pattern_temp is None:
            path = self.path_from_id()
            # "patterns[1].edges[7].handles[0]"   -> [("patterns",1), ("edges",7), ("handles",0)]
            segments = re.findall(r'(\w+)\[(\d+)\]', path)
            pattern_path = segments[0]
            if pattern_path[0] == "patterns":
                self.pattern_temp = self.id_data.patterns[int(pattern_path[1])]
        return self.pattern_temp

    @pattern.setter
    def pattern(self, value):
        self.pattern_temp = value


define_temp_prop(Vertex2D, "pattern_temp", None)
define_temp_prop(Vertex2D, "impacted", False)
define_temp_prop(Vertex2D, "proxy", None)

# EdgeType = [
#     ("BESSEL", "Bessel", "", 1),
#     ("CUBIC_SPLINE", "points", "", 2),  # cubic spline
# ]

HandleType = [
    ("ALIGNED", "Aligned", "Aligned handles", 0, 1),
    ("VECTOR", "Vector", "Vector handles", 0, 2),
    ("FREE", "Free", "Free handles", 0, 4),
]


class Edge2D(PropertyGroup, ModelData, Selectable):
    # type: EnumProperty(name="edgeType", items=EdgeType, default="BESSEL")
    vertex_index: IntVectorProperty(name="vertexIndex", size=2, default=(0, 0))
    handles: CollectionProperty(name="handles", type=Vertex2D, )
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

    @property
    def pattern(self):
        if self.pattern_temp is not None:
            try:
                self.pattern_temp.path_from_id()
            except Exception as e:
                console.error("can not get pattern!", e)
                self.pattern_temp = None
        if self.pattern_temp is None:
            path = self.path_from_id()
            # "patterns[1].edges[7].handles[0]"   -> [("patterns",1), ("edges",7), ("handles",0)]
            segments = re.findall(r'(\w+)\[(\d+)\]', path)
            pattern_path = segments[0]
            if pattern_path[0] == "patterns":
                self.pattern_temp = self.id_data.patterns[int(pattern_path[1])]
        return self.pattern_temp

    @pattern.setter
    def pattern(self, value):
        self.pattern_temp = value

    def reverse(self):
        self.vertex_index[0], self.vertex_index[1] = self.vertex_index[1], self.vertex_index[0]
        self.handle1.co[:], self.handle2.co[:] = self.handle2.co[:], self.handle1.co[:]
        self.handle1_type, self.handle2_type = self.handle2_type, self.handle1_type

    @property
    def handle1(self):
        if len(self.handles) < 1:
            self.handles.add()
        return self.handles[0]

    @property
    def handle2(self):
        if len(self.handles) < 2:
            if len(self.handles) < 1:
                self.handles.add()
            self.handles.add()
        return self.handles[1]

    @property
    def vertex0(self):
        return self.pattern.vertices[self.vertex_index[0]]

    @property
    def vertex1(self):
        return self.pattern.vertices[self.vertex_index[1]]

    def update(self, pattern=None):
        if not self.need_update_points:
            return
        if pattern is not None:
            self.pattern = pattern
        self.vertices[0] = self.vertex0.co[:]
        self.vertices[1] = self.vertex1.co[:]
        self.render_points = self.generate_render_points(1024)
        # self.calc_length()
        pts = self.render_points
        self.length = np.sum(np.linalg.norm(pts[1:] - pts[:-1], axis=1))
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
        from ..gizmos.curve_renderer import CurveRenderer
        if self.renderer is None:
            self.renderer = CurveRenderer(self)
        self.handle1.pattern = self.pattern
        self.handle2.pattern = self.pattern
        self.renderer.update_batch()

    def calc_bbox(self, points):
        bbox_min = points.min(axis=0)
        bbox_max = points.max(axis=0)
        # bpy.context.workspace.status_text_set(f"{self.geo_points_temp.min(axis=0)} {self.geo_points_temp.max(axis=0)}")
        self.bbox[0] = bbox_min[0]
        self.bbox[1] = bbox_min[1]
        self.bbox[2] = bbox_max[0]
        self.bbox[3] = bbox_max[1]

    @property
    def type(self):
        return "BESSEL" if len(self.spline_points) == 0 else "CUBIC_SPLINE"

    def add_edge_point(self, position):
        point = self.spline_points.add()
        point.co = position
        return point

    def generate_render_points(self, render_point_count=1024):
        h1 = None if self.handle1_type == "VECTOR" else self.handle1.co
        h2 = None if self.handle2_type == "VECTOR" else self.handle2.co
        edge_points = [p.co for p in self.spline_points]
        q = np.array((self.vertices[0], *edge_points, self.vertices[1]))
        return generate_curve_points(q, h1, h2, render_point_count).astype(np.float32)

    def sections(self):
        max_sec = 10000
        sec: Section = self.section_start
        if sec is None:
            self.pattern.recreate_sections()
            sec = self.section_start
        assert sec is not None, "Sections are not created!!!"
        while sec is not self.section_end and max_sec > 0:
            yield sec
            sec = sec.next
            max_sec -= 1
        if max_sec == 0:
            raise ValueError("Wrong section link!!")

    def calc_temp_geo_point(self, point_size):
        point_size = max(point_size, 2)
        temp_points = self.generate_render_points(max(point_size * 2, 8))
        self.geo_points_temp = resample_polyline(temp_points, [(0, point_size)], True)

    def calc_geo_point_for_sections(self):
        min_g = self.pattern.granularity
        sections = list(self.sections())
        for sec in sections:
            if sec.seg == -1:
                sec.seg = max(math.ceil(sec.absolute_length() / sec.edge.pattern.granularity), 1)
                # console.info("sec", sec.start_pos, sec.end_pos, sec.seg)
            # else:
            #     console.warning("sec", sec.start_pos, sec.end_pos, sec.seg)
            min_g = min(sec.absolute_length() / sec.seg, min_g)
        only_one_section = self.section_start.next == self.section_end
        if only_one_section:
            point_size = self.section_start.seg + 1
            self.calc_temp_geo_point(point_size)
            self.section_start.start_point = 0
        else:
            point_size = max(math.ceil(self.length / min_g), 1) + 1
            self.calc_temp_geo_point(point_size * 2)
            segments = []
            points_count = 0
            for i, sec in enumerate(sections):
                sec.start_point = points_count
                points_count += sec.seg
                segments.append([sec.start_pos, sec.seg])
            segments[-1][1] += 1
            # console.info("segments",sections, segments)
            self.geo_points_temp = resample_polyline(self.geo_points_temp, segments, True)
            # console.success(len(self.geo_points_temp))
        return

    def clear_temp_data(self):
        self.pattern = None
        self.need_update_points = True

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
        if max_sec == 10000:
            # a loop with only one section
            if pos - sec.start_pos < eps:
                return sec
            radio = (pos - sec.start_pos) / (sec.end_pos - sec.start_pos)
            _, new_sec = sec.split(radio)
            return new_sec
        return None

    # def try_regain_self(self):
    #     if self.pattern is not None and self.pattern.global_uuid != -1:
    #         self.pattern.forced_update()


define_temp_prop(Edge2D, "pattern_temp", None)
define_temp_prop(Edge2D, "length", None)
define_temp_prop(Edge2D, "vertices", lambda: [(0.0, 0.0), (0.0, 0.0)])
define_temp_prop(Edge2D, "need_update_points", True)
define_temp_prop(Edge2D, "render_points", None)
define_temp_prop(Edge2D, "renderer", None)
define_temp_prop(Edge2D, "geo_points_temp", None)
define_temp_prop(Edge2D, "unique_geo_point_size", 0)
define_temp_prop(Edge2D, "section_start", None)
define_temp_prop(Edge2D, "section_end", None)
define_temp_prop(Edge2D, "start_point", -1)
define_temp_prop(Edge2D, "proxy", None)

register, unregister = register_classes_factory((Vertex2D, Edge2D,))
