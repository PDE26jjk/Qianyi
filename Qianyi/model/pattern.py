import time
from collections import defaultdict, deque

import bpy
import numpy as np
from bpy.props import FloatVectorProperty, CollectionProperty, EnumProperty, IntVectorProperty, \
    FloatProperty, PointerProperty, BoolProperty, IntProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
from mathutils import Vector

from ..utilities.console import console_print, console
from ..utilities.report import report_error
from ..utilities.coords_transform import create_2d_matrix, create_2d_matrix_invert
from .geometry import Vertex2D, Edge2D
from .internal_line import InternalLine
from .section import Section
from ..utilities.node_tree import get_all_node_tree
from .. import global_data
from ..utilities.cubic_spline import cubic_spline_2d_numpy
from .model_data import ModelData, define_temp_prop, Selectable
from .pattern_mesh import generate_pattern_mesh


# Cached self-intersection state of a pattern outline. The answer comes from an
# engine call, so it is cached and the cache is a temp prop: a file that is
# reopened starts as unknown and is checked again on the next consumer.
VALIDITY_UNKNOWN = "UNKNOWN"
VALIDITY_VALID = "VALID"
VALIDITY_INVALID = "INVALID"


def boundary_self_intersection(points):
    """Test one closed boundary polyline for a self-crossing.

    `points` is the concatenated sampled outline (N x 2, in pattern space); the
    engine treats it as a loop, so the last point connects back to the first.
    Returns ``(intersected, crossing)``, where `crossing` is the intersection
    point in the same space, or None when there is none.
    """
    points = np.ascontiguousarray(points, dtype=np.float32)
    if points.ndim != 2 or points.shape[0] < 3:
        # Fewer than three points cannot enclose an area, which the engine
        # reports as an intersection ("one point or one edge").
        return True, None
    from Qianyi_DP import pattern_helper
    result = pattern_helper.check_edge_intersection(points.reshape(-1))
    if not result["intersected"]:
        return False, None
    index = int(result["res_index"])
    weight = float(result["res_weight"])
    if not 0 <= index < len(points):
        return True, None
    start = points[index]
    end = points[(index + 1) % len(points)]
    return True, (float(start[0] + (end[0] - start[0]) * weight),
                  float(start[1] + (end[1] - start[1]) * weight))


def interactive_edit_allowed(context, points):
    """Whether an interactive edit that produced `points` may be applied.

    False means the outline crosses itself, and the user is told why. The
    interactive operators are the only path that tests at edit time, and the
    scene's "Check Self-Intersection" switch turns that test off, so a new
    operator can be written without the check first. Nothing else needs the
    call: `forced_update` marks the outline unchecked on every shape change, and
    the mesh and the simulation test it before they use it.
    """
    scene = getattr(context, "scene", None)
    qmyi = getattr(scene, "qmyi", None)
    if qmyi is not None and not qmyi.interactive_self_intersection_check:
        return True
    intersected, _crossing = boundary_self_intersection(points)
    if not intersected:
        return True
    report_error("edges intersected!", (
        "turn off Check Self-Intersection in the Pattern panel to edit through it",
    ))
    return False


def find_invalid_patterns(patterns, force=False):
    """The patterns of `patterns` whose outline crosses itself.

    With `force` the outline is tested again even when the cached answer is
    known: a simulation start asks for that, so an operator that changed the
    outline without marking it cannot slip through. The mesh path uses the
    cache instead, so an edit pays for one test, not one per consumer.
    """
    invalid = []
    for pattern in patterns:
        if pattern.validate(force=force) == VALIDITY_INVALID and pattern not in invalid:
            invalid.append(pattern)
    return invalid


class Pattern(PropertyGroup, ModelData, Selectable):
    anchor: FloatVectorProperty(name="anchor", subtype="XYZ", size=2, default=(0.0, 0.0))
    rotation: FloatProperty(name="rotation", default=0.0, subtype='ANGLE', unit='ROTATION')
    grain_dir: FloatProperty(name="Grain Direction", default=0.0, subtype='ANGLE', unit='ROTATION')
    vertices: CollectionProperty(type=Vertex2D, name="vertices")
    edges: CollectionProperty(type=Edge2D, name="edges")
    internal_lines: CollectionProperty(type=InternalLine, name="internalLines")
    fabric_uuid: IntProperty(name="fabricUUID", default=-1)
    instance_next_uuid: IntProperty(name="Instance Next UUID", default=-1)
    is_mirror: BoolProperty(name="Is Mirror", default=False)
    collision_layer: IntProperty(
        name="CollisionLayer",
        description="When in contact, the higher level is above the lower level, along the normal direction of the lower level.",
        default=0)
    generator_uuid: IntProperty(
        name="Generator",
        description="Generator that produced this panel; -1 for a hand-drawn panel.",
        default=-1)

    def update_granularity(self, context):
        self.forced_update()

    granularity: FloatProperty(
        name="granularity",
        description="Sampling radius in millimetres. It is a ceiling on the "
                    "vertex spacing, not the resulting edge length: the median "
                    "edge is about 0.7x this value (5 mm gives a 3.6 mm mesh, "
                    "7 mm gives a 5.1 mm mesh)",
        default=20.0, update=update_granularity)
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
        f = global_data.get_obj_by_uuid(self.fabric_uuid)
        if f is None:
            self.project.refresh_collection_uuid(self.project.fabrics)
        f = global_data.get_obj_by_uuid(self.fabric_uuid)
        return f

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
        if global_data.renderers_enabled:
            from ..gizmos.pattern_renderer import PatternRenderer
            from ..gizmos.GizmosMeshRenderer import MeshRenderer
            self.line_renderer = PatternRenderer(self)
            self.mesh_renderer = MeshRenderer(self)
        for il in self.internal_lines:
            il.initialize()
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

        self.recreate_sections()
        self.forced_update()
        return ccw

    def mark_shape_changed(self):
        """Forget the cached outline state; the next consumer re-checks.

        Marking costs nothing: there is no engine call here, so a numeric field
        that passes through an illegal shape while it is typed is never blocked.
        """
        self.validity_state = VALIDITY_UNKNOWN
        self.invalid_point = None

    def get_boundary_points(self):
        """The closed outline as one (N, 2) float32 array in pattern space.

        Every edge contributes its sampled points except the last one, which is
        the next edge's first point, so the concatenation is exactly the loop
        the engine's self-intersection test expects. Internal lines are not part
        of it: an internal line crossing the outline is supported (the sections
        are split and the outside part is marked), not an error.
        """
        chunks = []
        for edge in self.edges:
            edge.update(self)
            points = edge.render_points
            if points is None or len(points) < 2:
                continue
            chunks.append(points[:-1])
        if len(chunks) == 0:
            return None
        return np.concatenate(chunks, dtype=np.float32)

    def check_self_intersection(self):
        """Run the outline test now and cache the result with the crossing."""
        points = self.get_boundary_points()
        if points is None:
            self.validity_state = VALIDITY_INVALID
            self.invalid_point = None
            return self.validity_state
        intersected, crossing = boundary_self_intersection(points)
        self.invalid_point = crossing
        self.validity_state = VALIDITY_INVALID if intersected else VALIDITY_VALID
        if intersected:
            console.warning(f"pattern {self.name} outline intersects itself")
        return self.validity_state

    def validate(self, force=False):
        """Cached state of the outline: only an unknown state costs a test."""
        if force or self.validity_state not in (VALIDITY_VALID, VALIDITY_INVALID):
            return self.check_self_intersection()
        return self.validity_state

    @property
    def is_invalid(self):
        """The cached answer, for the draw loop: never runs the test."""
        return self.validity_state == VALIDITY_INVALID

    def get_connected_patterns_and_sewings(self):
        # 1. 构建邻接表：记录每个 pattern 连接的 sewing 对象
        adj = defaultdict(list)
        for sewing in self.project.sewings:
            p1, p2 = sewing.pattern1, sewing.pattern2
            if p1 is None or p2 is None:
                continue
            adj[p1].append(sewing)
            if p1 != p2:
                adj[p2].append(sewing)

        # 2. 从 self 出发，进行 BFS 搜索
        visited_patterns = set()
        visited_sewings = set()  # 用于去重，因为一条 sewing 会被两个 pattern 共享
        queue = deque([self])

        while queue:
            curr = queue.popleft()
            if curr in visited_patterns:
                continue

            visited_patterns.add(curr)

            # 遍历与当前 pattern 相连的所有 sewing
            for sewing in adj[curr]:
                # 收集涉及的 sewing (利用 set 自动去重)
                visited_sewings.add(sewing)

                # 通过 sewing 找出相邻的 pattern
                neighbor = sewing.pattern2 if sewing.pattern1 == curr else sewing.pattern1
                if neighbor == curr:
                    continue
                # console.warning(neighbor,curr,neighbor is curr,neighbor == curr)
                # 如果相邻 pattern 未访问过，加入队列继续搜索
                if neighbor not in visited_patterns:
                    queue.append(neighbor)

        return visited_patterns, visited_sewings

    def update_connected_pattern_sewing_state(self):
        connected_patterns, _ = self.get_connected_patterns_and_sewings()
        if connected_patterns:
            for p in connected_patterns:
                p.need_sewing_update = True

    def forced_update(self, calc_intersect=True):
        self.mark_shape_changed()
        self.refresh_collection_uuid(self.edges)
        for edge in self.edges:
            edge.need_update_points = True
            edge.update(self)
        for line in self.internal_lines:
            self.refresh_collection_uuid(line.edges)
            line.update(self)
        self.calc_bbox()
        self.need_render_update = True
        if calc_intersect:
            self.handle_section_intersect()
        self.need_geo_update = True
        self.update_connected_pattern_sewing_state()

    def recreate_sections(self):
        for edge in self.edges:
            edge.section_start = Section(edge, 0., 1.)
        for i, edge in enumerate(self.edges):
            next_sec = self.edges[(i + 1) % len(self.edges)].section_start
            prev_sec = self.edges[(i - 1) % len(self.edges)].section_start
            edge.section_start.next = next_sec
            edge.section_start.prev = prev_sec
            edge.section_end = next_sec
        if len(self.internal_lines) > 0:
            for internal_line in self.internal_lines:
                for edge in internal_line.edges:
                    edge.section_start = Section(edge, 0., 1.)
                if internal_line.is_loop:
                    for i, edge in enumerate(internal_line.edges):
                        next_sec = internal_line.edges[(i + 1) % len(internal_line.edges)].section_start
                        prev_sec = internal_line.edges[(i - 1) % len(internal_line.edges)].section_start
                        edge.section_start.next = next_sec
                        edge.section_start.prev = prev_sec
                        edge.section_end = next_sec
                else:
                    for i, edge in enumerate(internal_line.edges):
                        next_sec = internal_line.edges[i + 1].section_start if i < len(
                            internal_line.edges) - 1 else None
                        prev_sec = internal_line.edges[i - 1].section_start if i > 0 else None
                        edge.section_start.next = next_sec
                        # console.warning(edge.section_start, "->", next_sec)
                        edge.section_start.prev = prev_sec
                        edge.section_end = next_sec

    def handle_section_intersect(self):
        if len(self.internal_lines) == 0:
            return
        edge_points = [self.get_geo_points_unique()]
        curve_sizes = [len(edge_points[0])]
        is_loops = [True]
        sec_point_sizes = [e.unique_geo_point_size for e in self.edges]
        sec_sizes = [len(self.edges)]
        for i, il in enumerate(self.internal_lines):
            il_edge_points = il.get_geo_points_unique()
            edge_points.append(il_edge_points)
            is_loops.append(il.is_loop)
            curve_sizes.append(len(il_edge_points))
            sec_point_sizes.extend([e.unique_geo_point_size for e in il.edges])
            sec_sizes.append(len(il.edges))

        edge_points = np.concatenate(edge_points).astype(np.float32)
        curve_sizes = np.array(curve_sizes, dtype=np.int32)
        is_loops = np.array(is_loops, dtype=np.int8)
        from Qianyi_DP import pattern_helper
        intersections = pattern_helper.get_all_intersections(edge_points, curve_sizes, is_loops,
                                                             np.array(sec_sizes, np.int32),
                                                             np.array(sec_point_sizes, dtype=np.int32))
        insecs = []
        for intersection in intersections:
            console.info("intersection", intersection)
            (curve_a, section_a, t_a, curve_b,
             section_b, t_b, state) = (intersection['curve_a'],
                                       intersection['section_a'], intersection['t_a'],
                                       intersection['curve_b'],
                                       intersection['section_b'], intersection['t_b'],
                                       intersection['state'])
            insecs.append((curve_a, section_a, t_a, 0))
            insecs.append((curve_b, section_b, t_b, state))
        insecs.sort()
        secs = set()
        edges_update = set()
        il_split = set()
        for intersection in insecs:
            curve, sec_ind, t, state = intersection
            if curve == 0:
                edge = self.edges[sec_ind]
            else:
                edge = self.internal_lines[curve - 1].edges[sec_ind]
            sec = edge.section_start
            sec.pending_split.append((t, state))
            edges_update.add(edge)
            secs.add(sec)
            if state != 0:
                il_split.add(curve - 1)

        for sec in secs:
            sec.split_pending()
        for il_ind in il_split:
            il = self.internal_lines[il_ind]
            sec: Section = il.edges[0].section_start
            end_sec = None if not il.is_loop else sec
            start = False
            secs = []
            max_secs = 1000
            while (sec is not end_sec or not start) and max_secs > 0:
                start = True
                secs.append(sec)
                sec = sec.next
                max_secs -= 1
            if max_secs == 0:
                raise Exception("?????????")
            secs_split = [i for i, sec in enumerate(secs) if sec.io_state != 0]
            if secs[secs_split[0]].io_state == 2:
                for i in range(secs_split[0]):
                    secs[i].outsize = True
            if secs[secs_split[-1]].io_state == 1:
                for i in range(secs_split[-1], len(secs)):
                    secs[i].outsize = True
            if len(secs_split) > 1:
                for i in range(len(secs_split) - 1):
                    if secs[secs_split[i]].io_state == 1:
                        for j in range(secs_split[i], secs_split[i + 1]):
                            secs[j].outsize = True
            states = [sec.io_state for sec in secs]
            outsizes = [sec.outsize for sec in secs]
            # console.info(states)
            # console.info(outsizes)

        for edge in edges_update:
            edge.need_update_points = True
            edge.update(self)

    def gen_mesh_edge_points_and_sections(self):
        sections = []
        points = self.get_geo_points_unique()
        start_point_final = 0
        for e in self.edges:
            edge_sections = list(e.sections())
            sections.extend(edge_sections)
            for sec in edge_sections:
                sec: Section
                sec.mesh_start_point = start_point_final
                sec.continuous = True
                start_point_final += sec.seg
                # console.info("sec.seg", sec.seg)
        if start_point_final != len(points):
            raise Exception("start_point_final != len(points)", start_point_final, len(points))
        sections[-1].mesh_end_point = 0
        return points, sections

    def calc_mesh_edge_points(self):
        edge_points, edge_sections = self.gen_mesh_edge_points_and_sections()
        secion_index_offset = len(edge_points)
        self.mesh_edge_point_outer_size = secion_index_offset
        edge_points = [edge_points]

        for i, il in enumerate(self.internal_lines):
            for edge in il.edges:
                edge.update(self) # points may be changed after handling sewings.
            il_edge_points, il_sections = il.gen_inside_points_and_sections(secion_index_offset)
            secion_index_offset += len(il_edge_points)
            edge_points.append(il_edge_points)
            edge_sections.extend(il_sections)

        edge_points = np.concatenate(edge_points).astype(np.float32)

        from Qianyi_DP import pattern_helper
        threshold = self.granularity * 0.02
        mesh_edge_points, mesh_edge_index_map = pattern_helper.deduplicate_points(edge_points, threshold=threshold)
        mesh_edge_points = mesh_edge_points.reshape((-1, 2))
        self.mesh_edge_points = mesh_edge_points
        self.mesh_edge_index_map = mesh_edge_index_map

        edge_indices = self.calculate_edge_indices_by_sections(edge_sections)
        # console.info("edge_indices",edge_indices,mesh_edge_index_map,len(mesh_edge_points))
        self.mesh_edge_point_indices = mesh_edge_index_map[edge_indices].astype(np.int32)
        # self.mesh_edge_sizes = edge_points
        self.need_geo_update = False

    def calculate_edge_indices_by_sections(self, edge_sections):
        edge_indices = []
        for sec in edge_sections:
            sec: Section
            indices = np.array([(i, i + 1) for i in range(sec.seg)]) + sec.mesh_start_point
            if sec.mesh_end_point != -1:
                indices[-1][1] = sec.mesh_end_point
            edge_indices.append(indices)
        edge_indices = np.concatenate(edge_indices).astype(np.int32)
        return edge_indices
        # TODO test it
        # if not edge_sections:
        #     edge_indices = np.empty((0, 2), dtype=np.int32)
        # else:
        #     # 1. 单次遍历提取属性，避免多次循环和零散的内存分配
        #     data = np.array(
        #         [(sec.seg, sec.mesh_start_point, sec.mesh_end_point) for sec in edge_sections],
        #         dtype=np.int32
        #     )
        #     segs = data[:, 0]
        #     start_pts = data[:, 1]
        #     end_pts = data[:, 2]
        #
        #     total_edges = segs.sum()
        #     if total_edges == 0:
        #         edge_indices = np.empty((0, 2), dtype=np.int32)
        #     else:
        #         # 2. 计算每个 Section 在全局边数组中的起始偏移量
        #         sec_start_edge_idx = np.zeros(len(segs), dtype=np.int32)
        #         sec_start_edge_idx[1:] = np.cumsum(segs[:-1])
        #
        #         # 3. 将全局边的 ID 映射回所属的 Section ID 和 Section 内的局部 ID
        #         # section_ids: 长度为 total_edges，指明每条边属于哪个 section
        #         # local_k: 长度为 total_edges，指明每条边在 section 内的索引 (0 ~ seg-1)
        #         section_ids = np.repeat(np.arange(len(segs), dtype=np.int32), segs)
        #         local_k = np.arange(total_edges, dtype=np.int32) - np.repeat(sec_start_edge_idx, segs)
        #
        #         # 4. 向量化计算原始点索引 (等同于原逻辑中的 indices + sec.mesh_start_point)
        #         sec_start_pts = start_pts[section_ids]
        #         raw_col0 = sec_start_pts + local_k
        #         raw_col1 = sec_start_pts + local_k + 1
        #
        #         # 5. 处理 mesh_end_point 覆盖逻辑 (仅覆盖每个 section 的最后一条边的 col1)
        #         override_mask = (end_pts != -1) & (segs > 0)  # 加上 segs > 0 防止空 section 越界
        #         if np.any(override_mask):
        #             # 找到需要覆盖的全局边索引：该 section 的起始索引 + segs - 1
        #             last_edge_global_idx = sec_start_edge_idx + segs - 1
        #             # 直接利用高级索引进行覆盖
        #             raw_col1[last_edge_global_idx[override_mask]] = end_pts[override_mask]
        #
        #         # 6. 组合成 (N, 2) 的索引数组，并通过 mesh_point_indeices 映射
        #         raw_indices = np.stack((raw_col0, raw_col1), axis=-1)
        #         edge_indices = mesh_point_indeices[raw_indices]

    def add_vertex(self, position):
        """添加顶点"""
        vertex = self.vertices.add()
        vertex.pattern = self
        vertex.co = position
        return len(self.vertices) - 1

    def add_edge(self, start_idx, end_idx, control1=None, control2=None, handle1_type="VECTOR",
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
            render_points.append(points)
        self.render_points = np.concatenate(render_points, dtype=np.float32)
        self.line_renderer.update_batch_edge(self.render_points)
        for il in self.internal_lines:
            il.update_render_line()
        return self.render_points

    def update_render_vertex(self):
        if not self.initialized:
            self.initialize()
            self.initialized = True

        self.line_renderer.update_batch_vertex(self.get_vertice_list())

    def update_render_spline_point(self):
        points = []
        for edge in self.edges:
            if len(edge.spline_points) > 0:
                points.append([p.co for p in edge.spline_points])
        if len(points) > 0:
            points = np.concatenate(points, dtype=np.float32)
        self.line_renderer.update_batch_spline_point(points)
        for il in self.internal_lines:
            il.update_render_spline_point()

    def get_geo_points_unique(self):
        edge_points = []
        start_point = 0
        for i in range(len(self.edges)):
            e = self.edges[i]
            e.update(self)
            points = e.geo_points_temp[:-1]
            if points.shape[0] < 1:
                console.warning(e.vertex0.co, e.handle1_type, e.vertex1.co, e.handle2_type)
                raise Exception("points.shape[0] < 1")
            edge_points.append(points)
            e.start_point = start_point
            e.unique_geo_point_size = len(points)
            start_point += points.shape[0]
        edge_points = np.concatenate(edge_points, dtype=np.float32)
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
        return np.array(((self.bbox[0], self.bbox[1]), (self.bbox[2], self.bbox[3])), dtype=np.float32)

    @property
    def center(self):
        bbox = self.get_bbox()
        return (bbox[0] + bbox[1]) * 0.5

    def generate_mesh(self, scale_data=None):
        granularity = self.granularity / 1000
        # A crossing outline cannot become a mesh at all. The sampler does not
        # only drop the triangles it cannot validate: on a bowtie outline it
        # takes the engine down with an illegal memory access in the 2D BVH
        # (`lbvh_2d.cu`), and that fault only surfaces on the next engine call.
        # So the mesh is not generated and the pattern keeps whatever mesh it
        # had; the outline is drawn red and a simulation will not start.
        if self.validate() == VALIDITY_INVALID:
            console.warning(f"pattern {self.name or '(unnamed)'}: mesh not regenerated, "
                            f"the outline is invalid")
            return
        start = time.time()
        if self.need_geo_update:
            self.calc_mesh_edge_points()
        self.mesh_object = generate_pattern_mesh(self, granularity, self.mesh_object,
                                                 scale_data)
        if self.name:
            self.mesh_object.name = self.name
            self.mesh_object.data.name = self.name
        console_print("generate_pattern_mesh: ", time.time() - start)
        console_print("generated: ", self.mesh_object.name)
        start = time.time()
        sim_pros = self.mesh_object.qmyi_simulation_props
        # console_print(sim_pros.id_data)
        sim_pros.participate_in_simulation = True
        sim_pros.pattern = self
        sim_pros.ensure_attributes()
        if global_data.renderers_enabled:
            if self.mesh_renderer is None:
                from ..gizmos.GizmosMeshRenderer import MeshRenderer
                self.mesh_renderer = MeshRenderer(self)
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
        self.impacted = False

    def calc_inv_matrix(self):
        self.inv_transform_mat_2D = create_2d_matrix_invert(scale=(-1 if self.is_mirror else 1, 1),
                                                            rotation=self.rotation, offset=self.anchor)
        return self.inv_transform_mat_2D

    def calc_matrix(self):
        self.transform_mat_2D = create_2d_matrix(scale=(-1 if self.is_mirror else 1, 1), rotation=self.rotation,
                                                 offset=self.anchor)
        return self.transform_mat_2D

    def view_to_pattern_pos(self, pos):
        pos = self.calc_inv_matrix() @ Vector((pos[0], pos[1], 0, 1))
        return pos[0], pos[1]

    def pattern_to_view_pos(self, pos):
        pos = self.calc_matrix() @ Vector((pos[0], pos[1], 0, 1))
        return pos[0], pos[1]

    def copy_pattern(self, as_instance=False, mirror=False, project=None):
        if project is None:
            project = self.project

    def other_instances(self):
        instances = []
        if self.instance_next_uuid == -1:
            return instances
        p = global_data.get_obj_by_uuid(self.instance_next_uuid)
        # if p is None:
        #     self.instance_next_uuid = -1
        #     return instances
        while p.global_uuid != self.global_uuid:
            instances.append(p)
            p = global_data.get_obj_by_uuid(p.instance_next_uuid)
        return instances


define_temp_prop(Pattern, "initialized", False)
define_temp_prop(Pattern, "need_render_update", True)
define_temp_prop(Pattern, "need_geo_update", True)
define_temp_prop(Pattern, "need_sewing_update", True)
# define_temp_prop(Pattern, "connected_patterns", None)
define_temp_prop(Pattern, "render_points", [])
# define_temp_prop(Pattern, "triangles", [])
# define_temp_prop(Pattern, "point2edge", [])
define_temp_prop(Pattern, "mesh_renderer", None)
define_temp_prop(Pattern, "line_renderer", None)
define_temp_prop(Pattern, "transform_mat_2D", None)
define_temp_prop(Pattern, "inv_transform_mat_2D", None)
define_temp_prop(Pattern, "instances", None)
define_temp_prop(Pattern, "impacted", False)
define_temp_prop(Pattern, "mesh_edge_points", None)
define_temp_prop(Pattern, "mesh_edge_index_map", None)
define_temp_prop(Pattern, "mesh_point_indices", None)
define_temp_prop(Pattern, "mesh_edge_point_outer_size", -1)
# Outline validity. A temp prop on purpose: it is a cache of an engine answer,
# so it is never written to the file and a reopened scene starts as unknown.
define_temp_prop(Pattern, "validity_state", VALIDITY_UNKNOWN)
define_temp_prop(Pattern, "invalid_point", None)

register, unregister = register_classes_factory((Pattern,))
