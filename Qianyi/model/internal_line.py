import re

import numpy as np
from bpy.props import CollectionProperty, BoolProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .section import Section
from .geometry import Edge2D
from .model_data import ModelData, define_temp_prop, Selectable
from .. import global_data
from ..utilities.console import console


class InternalLine(PropertyGroup, ModelData, Selectable):
    edges: CollectionProperty(type=Edge2D, name="edges")
    is_loop: BoolProperty(name="is_loop", default=False)
    is_hole: BoolProperty(name="is_hole", default=False)

    def initialize(self):
        pattern = self.pattern
        for edge in self.edges:
            edge.pattern = pattern
            edge.initialize()
        if global_data.renderers_enabled:
            from ..gizmos.internal_line_renderer import InternalLineRenderer
            self.renderer = InternalLineRenderer(self)

    def update(self, pattern):  # only call in pattern.forced_update
        self.pattern = pattern
        for edge in self.edges:
            edge.need_update_points = True
            edge.update(pattern)
        if global_data.renderers_enabled and self.renderer is None:
            from ..gizmos.internal_line_renderer import InternalLineRenderer
            self.renderer = InternalLineRenderer(self)

    def update_render_spline_point(self):
        points = []
        for edge in self.edges:
            if len(edge.spline_points) > 0:
                points.append([p.co for p in edge.spline_points])
        if len(points) > 0:
            points = np.concatenate(points, dtype=np.float32)
        self.renderer.update_batch_spline_point(points)

    def update_render_line(self):
        render_points = []
        for i in range(len(self.edges)):
            self.edges[i].update(self.pattern)
            points = self.edges[i].render_points
            render_points.append(points)
        self.render_points = np.concatenate(render_points, dtype=np.float32)
        self.renderer.update_batch_edge(self.render_points)
        return self.render_points

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

    def add_edge(self, start_idx, end_idx,
                 control1=None, control2=None, handle1_type="VECTOR",
                 handle2_type="VECTOR", update=True):
        edge: Edge2D = self.edges.add()
        edge.vertex_index[0] = start_idx
        edge.vertex_index[1] = end_idx
        if control1 is not None and control2 is not None:
            edge.handle1.co = control1[:]
            edge.handle2.co = control2[:]
        edge.handle1_type = handle1_type
        edge.handle2_type = handle2_type
        edge.pattern = self
        if update:
            edge.update(self)
        return edge

    def get_inside_sections(self):
        sections = []
        for edge in self.edges:
            sections.extend([sec for sec in edge.sections() if not sec.outsize])
        return sections

    def gen_inside_points_and_sections(self, index_offset=0):
        sections = self.get_inside_sections()
        edge_points = []
        start_point_final = index_offset
        self.mesh_edge_inner_point_size = np.sum([sec.seg for sec in sections])
        for i, sec in enumerate(sections):
            sec: Section
            if i < len(sections) - 1 and sec.next is sections[i + 1]:  # Continuous, shared vertex
                points = sec.edge.geo_points_temp[sec.start_point:sec.start_point + sec.seg]
                sec.continuous = True
            else:
                points = sec.edge.geo_points_temp[sec.start_point:sec.start_point + sec.seg + 1]
                sec.continuous = False
            edge_points.append(points)
            sec.mesh_start_point = start_point_final
            start_point_final += len(points)
        edge_points = np.concatenate(edge_points, dtype=np.float32)
        if self.is_loop and sections[-1].next is sections[0]:
            sections[-1].mesh_end_point = index_offset

        return edge_points, sections

    def get_geo_points_unique(self):
        edge_points = []
        start_point = 0
        for i in range(len(self.edges)):
            e = self.edges[i]
            e.update(self)
            if not self.is_loop and i == len(self.edges) - 1:
                points = e.geo_points_temp[:]  # no-loop retain last point.
            else:
                points = e.geo_points_temp[:-1]  # loop overlap last point, remove it.
            if points.shape[0] < 1:
                console.warning(e.vertex0.co, e.handle1_type, e.vertex1.co, e.handle2_type)
                raise Exception("points.shape[0] < 1")
            e.unique_geo_point_size = len(points)
            edge_points.extend(points)
            e.start_point = start_point
            start_point += points.shape[0]
        return edge_points


define_temp_prop(InternalLine, "pattern_temp", None)
define_temp_prop(InternalLine, "render_points", None)
define_temp_prop(InternalLine, "renderer", None)
define_temp_prop(InternalLine, "mesh_edge_inner_point_size", -1)

register, unregister = register_classes_factory((InternalLine,))
