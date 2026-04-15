import time
import bpy
import numpy as np
from bpy.props import FloatVectorProperty, CollectionProperty, EnumProperty, IntVectorProperty, \
    FloatProperty, PointerProperty, BoolProperty, IntProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
from mathutils import Vector

from utilities.console import console_print, console
from utilities.coords_transform import create_2d_matrix, create_2d_matrix_invert
from .geometry import Vertex2D, Edge2D
from .section import Section
from ..utilities.node_tree import get_all_node_tree
from .. import global_data
from ..utilities.cubic_spline import cubic_spline_2d_numpy
from .model_data import ModelData, define_temp_prop, Selectable
from .pattern_mesh import generate_pattern_mesh


class Pattern(PropertyGroup, ModelData, Selectable):
    anchor: FloatVectorProperty(name="anchor", subtype="XYZ", size=2, default=(0.0, 0.0))
    rotation: FloatProperty(name="rotation", default=0.0)
    vertices: CollectionProperty(type=Vertex2D, name="vertices")
    edges: CollectionProperty(type=Edge2D, name="edges")
    internal_lines: CollectionProperty(type=Edge2D, name="internalLines")
    fabric_uuid: IntProperty(name="fabricUUID", default=-1)

    def update_granularity(self, context):
        self.forced_update()

    granularity: FloatProperty(name="granularity", default=20.0, update=update_granularity)
    bbox: FloatVectorProperty(name="BBox", size=4, default=(0.0, 0.0, 1.0, 1.0))
    mesh_object: PointerProperty(
        name="Mesh Object",
        description="Reference to a mesh object",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH'
    )

    @property
    def fabric(self):
        if self.fabric_uuid == -1:
            default_fabric = self.project.get_default_fabric()
            assert default_fabric.project == self.project
            self.fabric_uuid = default_fabric.global_uuid
        assert self.fabric_uuid != -1
        return global_data.get_obj_by_uuid(self.fabric_uuid)

    @fabric.setter
    def fabric(self, val):
        assert val.global_uuid != -1
        self.fabric_uuid = val.global_uuid

    def initialize(self):
        for edge in self.edges:
            edge.pattern = self
            edge.initialize()
        for vertex in self.vertices:
            vertex.pattern = self
        from ..gizmos.pattern_renderer import PatternRenderer
        from ..gizmos.GizmosMeshRenderer import MeshRenderer
        self.line_renderer = PatternRenderer(self)
        self.mesh_renderer = MeshRenderer(self)
        self.calc_bbox()

    def calc_area(self):
        points = np.array(self.get_geo_points_unique())
        x = points[:, 0]
        y = points[:, 1]

        # 计算有向面积
        # 使用公式: A = 1/2 * Σ(x_i*y_{i+1} - x_{i+1}*y_i)
        # 其中 i 从 0 到 n-1，当 i = n-1 时，i+1 为 0

        # 创建索引数组
        n = len(points)
        i = np.arange(n)
        j = (i + 1) % n  # 下一个顶点的索引，循环处理

        # 计算有向面积
        area = 0.5 * np.sum(x[i] * y[j] - x[j] * y[i])
        return area

    def ensure_edge_ccw(self):
        self.refresh_collection_uuid(self.edges)
        ccw = True
        if self.calc_area() < 0:
            ccw = False
            console.warning("not ccw")
            for edge in self.edges:
                edge.reverse()
            count = len(self.edges)
            for i in range(count - 1):
                self.edges.move(count - 1, i)
        else:
            console.success("ccw")

        self.forced_update()
        return ccw

    def forced_update(self):
        self.refresh_collection_uuid(self.edges)
        for edge in self.edges:
            edge.need_update_points = True
            edge.update(self)
        self.calc_bbox()
        self.need_render_update = True

    def create_sections(self):
        for edge in self.edges:
            edge.section_start = Section(edge, 0., 1.)
        for i, edge in enumerate(self.edges):
            next_sec = self.edges[(i + 1) % len(self.edges)].section_start
            prev_sec = self.edges[(i - 1) % len(self.edges)].section_start
            edge.section_start.next = next_sec
            edge.section_start.prev = prev_sec
            edge.section_end = next_sec
        # TODO calculate edge-internal_lines intersect

    def add_vertex(self, position):
        """添加顶点"""
        vertex = self.vertices.add()
        vertex.pattern = self
        vertex.co = position
        return len(self.vertices) - 1

    def add_edge(self, start_idx, end_idx, edge_type="BESSEL", control1=None, control2=None, handle1_type="VECTOR",
                 handle2_type="VECTOR", update=True):
        """添加边"""
        edge: Edge2D = self.edges.add()
        edge.vertex_index[0] = start_idx
        edge.vertex_index[1] = end_idx
        edge.type = edge_type
        if control1 is not None and control2 is not None:
            edge.handle1.co = control1[:]
            edge.handle2.co = control2[:]
        edge.handle1_type = handle1_type
        edge.handle2_type = handle2_type
        # bpy.context.workspace.status_text_set(f"{edge.handle_type1} {handle_type1}")
        edge.pattern = self
        if update:
            edge.update(self)
            self.calc_bbox()
        return edge

    def update_render_line(self):
        if not self.initialized:
            self.initialize()
            self.initialized = True

        if len(self.vertices) < 2:
            return []
        render_points = []
        for i in range(len(self.edges)):
            self.edges[i].update(self)
            points = self.edges[i].render_points
            render_points.extend(points)
        self.render_points = render_points
        self.line_renderer.update_batch_edge(render_points)
        return self.render_points

    def update_render_vertex(self):
        if not self.initialized:
            self.initialize()
            self.initialized = True

        self.line_renderer.update_batch_vertex(self.get_vertice_list())

    def get_geo_points_unique(self):
        edge_points = []
        start_point = 0
        for i in range(len(self.edges)):
            e = self.edges[i]
            e.update(self)
            points = e.geo_points_temp[:-1]
            if points.shape[0] < 1:
                console.warning(e.vertex0.co,e.handle1_type,e.vertex1.co,e.handle2_type)
                raise Exception("points.shape[0] < 1")
            # console.warning('geo_points_temp', points)
            edge_points.extend(points)
            e.start_point = start_point
            start_point += points.shape[0]
        return edge_points

    def get_edge_geo_points(self):
        edge_points = []
        for i in range(len(self.edges)):
            self.edges[i].update(self)
            points = self.edges[i].geo_points_temp
            edge_points.extend(points)
        return edge_points

    def get_vertice_list(self):
        list_vertices = []
        for vertex in self.vertices:
            list_vertices.append(vertex.co)
        return list_vertices

    def transform(self, matrix):
        """应用变换矩阵"""
        self.anchor = matrix @ self.anchor

    def calc_bbox(self):
        points = np.asarray(self.get_edge_geo_points())
        if points.shape[0] > 0:
            bbox_min = points.min(axis=0)
            bbox_max = points.max(axis=0)
            self.bbox[0] = bbox_min[0]
            self.bbox[1] = bbox_min[1]
            self.bbox[2] = bbox_max[0]
            self.bbox[3] = bbox_max[1]

    def get_bbox(self):
        return (self.bbox[0], self.bbox[1]), (self.bbox[2], self.bbox[3])

    def generate_mesh(self):
        granularity = self.granularity / 1000
        start = time.time()
        self.mesh_object = generate_pattern_mesh(self.get_geo_points_unique(), granularity, self.mesh_object)
        console_print("generate_pattern_mesh: ", time.time() - start)
        console_print("generated: ", self.mesh_object.name)
        start = time.time()
        sim_pros = self.mesh_object.qmyi_simulation_props
        console_print(sim_pros.id_data)
        sim_pros.participate_in_simulation = True
        sim_pros.pattern = self
        sim_pros.ensure_attributes()
        if self.mesh_renderer is None:
            from ..gizmos.GizmosMeshRenderer import MeshRenderer
            self.mesh_renderer = MeshRenderer()
        self.mesh_renderer.create_batch(self.mesh_object)
        console_print("mesh_renderer.create_batch: ", time.time() - start)

    @property
    def project(self):
        return self.id_data

    def clear_temp_data(self):
        self.initialized = False
        self.need_render_update = True
        self.mesh_renderer = None
        self.line_renderer = None
        self._project = None

    def calc_inv_matrix(self):
        self.inv_transform_mat_2D = create_2d_matrix_invert(rotation=self.rotation, offset=self.anchor)
        return self.inv_transform_mat_2D

    def calc_matrix(self):
        self.transform_mat_2D = create_2d_matrix(rotation=self.rotation, offset=self.anchor)
        return self.transform_mat_2D

    def view_to_pattern_pos(self, pos):
        pos = self.calc_inv_matrix() @ Vector((pos[0], pos[1], 0, 1))
        return pos[0], pos[1]

    def pattern_to_view_pos(self, pos):
        pos = self.calc_matrix() @ Vector((pos[0], pos[1], 0, 1))
        return pos[0], pos[1]

define_temp_prop(Pattern, "initialized", False)
define_temp_prop(Pattern, "need_render_update", True)
define_temp_prop(Pattern, "need_geo_update", True)
define_temp_prop(Pattern, "render_points", [])
# define_temp_prop(Pattern, "triangles", [])
# define_temp_prop(Pattern, "point2edge", [])
define_temp_prop(Pattern, "mesh_renderer", None)
define_temp_prop(Pattern, "line_renderer", None)
define_temp_prop(Pattern, "transform_mat_2D", None)
define_temp_prop(Pattern, "inv_transform_mat_2D", None)

register, unregister = register_classes_factory((Pattern,))
