import time
import math
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
from ..utilities.geometric_operation import resample_polyline
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
    call: `mark_geometry_changed` marks the outline unchecked on every shape
    change, and the mesh and the simulation test it before they use it.
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


def crossing_check_enabled(context) -> bool:
    """Whether an interactive edit tests its result for a self-crossing.

    The scene's Check Self-Intersection switch is the one place the test is
    optional, and an operator that can produce a crossing reads it here: with
    the switch off, an edit that crosses is written like any other and the mesh
    stage is what reports it, which is how a pattern maker edits through a
    crossing on purpose. A context that cannot answer (a script, a headless
    run) counts as testing.
    """
    qmyi = getattr(getattr(context, "scene", None), "qmyi", None)
    if qmyi is None:
        return True
    return bool(qmyi.interactive_self_intersection_check)


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
    # The authored geometry is one Sketch per instance chain; a pattern reads it
    # through the properties below and never holds a copy of its own.
    sketch_uuid: IntProperty(name="Sketch", default=-1, options={"HIDDEN"})
    # The boundary samples this panel's last mesh was built from, kept as a copy
    # in the file. Session data would do for the editor, but a check that runs
    # without opening the add-on - a script reading the saved file - can only see
    # what was written, and this is the panel's own shape at its own granularity.
    geo_points: CollectionProperty(type=Vertex2D, name="geoPoints")
    fabric_uuid: IntProperty(name="fabricUUID", default=-1)
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
        """A granularity change resamples this panel and meshes it again.

        The number the user just typed is what this panel's samples and its mesh
        are built from, before the change returns. The other members of its
        chain keep their own granularity and their own mesh: the number is a
        panel's field, not something its copies follow.
        """
        self.mark_samples_changed()
        if self.mesh_object is not None:
            # A panel that has never been meshed is built by whoever asks for
            # its first mesh; meshing here would run in the middle of a script
            # that is still writing the panel.
            self.generate_mesh()

    @property
    def sketch(self):
        """The Sketch this pattern's geometry lives in, or None when it has none."""
        if self.sketch_uuid == -1:
            return None
        sketch = global_data.get_obj_by_uuid(self.sketch_uuid, check_uuid=False)
        if sketch is not None:
            return sketch
        # Undo, redo and a file reload clear the identity map, and a panel that
        # names a Sketch has to find it again without one: the project's
        # collection is the other half of the reference.
        for candidate in self.id_data.sketches:  # loop: one comparison per Sketch
            if candidate.global_uuid == self.sketch_uuid:
                global_data.uuid2obj[self.sketch_uuid] = candidate
                return candidate
        return None

    @sketch.setter
    def sketch(self, value):
        self.sketch_uuid = value.global_uuid if value is not None else -1

    def require_sketch(self):
        """The Sketch this pattern reads, refusing when it carries none.

        A panel with no Sketch has no geometry: nothing invents one for it, so
        a caller that asks for its points is told why instead of getting an
        empty shape.
        """
        sketch = self.sketch
        if sketch is None:
            raise RuntimeError(
                f"pattern {self.name!r} has no Sketch, so it has no geometry")
        return sketch

    @property
    def vertices(self):
        """This pattern's points: the collection of the Sketch it uses."""
        return self.require_sketch().vertices

    @property
    def edges(self):
        """This pattern's edges: the collection of the Sketch it uses."""
        return self.require_sketch().edges

    @property
    def internal_lines(self):
        """This pattern's internal lines: those of the Sketch it uses."""
        return self.require_sketch().internal_lines

    granularity: FloatProperty(
        name="granularity",
        description="Sampling radius in millimetres. ",
        default=20.0, update=update_granularity, min=0.5)
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
        sketch = self.sketch
        if sketch is not None:
            if sketch.owner is None:
                sketch.owner = self
            sketch.initialize()
        if global_data.renderers_enabled:
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

        self.mark_geometry_changed()
        return ccw

    def mark_shape_changed(self):
        """Forget the cached outline state; the next consumer re-checks.

        Marking costs nothing: there is no engine call here, so a numeric field
        that passes through an illegal shape while it is typed is never blocked.
        """
        self.validity_state = VALIDITY_UNKNOWN
        self.invalid_point = None
        # A shape change earns a new mesh attempt: the reason the last one was
        # refused no longer describes what the panel is now.
        self.mesh_error = None

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
            edge.update()
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
        """The cached answer, for the draw loop: never runs a test or a mesh."""
        return bool(self.mesh_error) or self.validity_state == VALIDITY_INVALID

    def get_connected_patterns_and_sewings(self):
        """The panels and sewings this panel's seam graph reaches.

        A seam side names its panel by identity, so a side whose panel an editor
        removed reads back as None and the walk skips it rather than touching
        what is not there.
        """
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
                if neighbor is None or neighbor == curr:
                    continue
                # console.warning(neighbor,curr,neighbor is curr,neighbor == curr)
                # 如果相邻 pattern 未访问过，加入队列继续搜索
                if neighbor not in visited_patterns:
                    queue.append(neighbor)

        return visited_patterns, visited_sewings

    def update_connected_pattern_sewing_state(self):
        connected_patterns, _ = self.get_connected_patterns_and_sewings()
        for p in connected_patterns:
            p.need_sewing_update = True

    def mark_geometry_changed(self):
        """The geometry this panel reads changed: its derived data is stale.

        Marking, not rebuilding: the outline is unchecked, and this panel's own
        copy of the section stage, its samples and its render line are marked.
        The consumers do the work - `ensure_sections` refreshes the Sketch's
        stage and clones this panel's copy from it, the mesh path runs that
        before it samples - so a tool that has to mesh at once still does, and a
        change that moves no geometry costs nothing here.

        The patches a seam cuts into this panel's copy are dropped by that
        rebuild: they were cut against the pieces the old geometry had, so a
        rebuild clones the stage as it is now and the linking run cuts again.
        """
        self.mark_shape_changed()
        if self.sketch is not None:
            # The curves are this panel's geometry as it is drawn, and the draw
            # path, the outline test and the measuring passes all read them: say
            # they moved, so the next reader of an edge builds it again.
            self.sketch.mark_curves_changed()
            # The edit itself is counted where it is written - a tool's write
            # helper calls `Sketch.touch`, and so does a write of a curve
            # (`Edge2D.set_curve`) - not here: marking a panel a consumer walks
            # past (a prepare does that) is not an edit, and counting it would
            # invalidate the baked data for nothing.
            self.need_sections = True
        self.need_render_update = True
        self.need_geo_update = True
        self.update_connected_pattern_sewing_state()

    def mark_sections_changed(self) -> None:
        """The seam graph this panel is part of changed: its copy is stale.

        The geometry did not move, so the curves and the outline's state stay as
        they are; only this panel's copy of the stage, its samples and its mesh
        are marked, and every panel the sewings reach is marked with it. A seam
        edit costs this much, which is what lets it leave the meshes alone until
        a consumer needs them.
        """
        self.need_sections = True
        self.need_geo_update = True
        self.need_render_update = True
        self.update_connected_pattern_sewing_state()

    def mark_samples_changed(self) -> None:
        """This panel's samples and its mesh are out of date; nothing else.

        A field that changes the sampling rather than the geometry - the
        granularity - needs exactly this: the pieces are cut at the same places,
        the seam graph did not move, the Sketch is untouched and no edit is
        counted. The section copy is rebuilt with it because a piece's segment
        count is what the new number decides.
        """
        self.need_sections = True
        self.need_geo_update = True
        self.need_render_update = True

    # ------------------------------------------- this panel's sections and samples

    def ensure_sections(self) -> None:
        """Build this panel's sections and samples when they are missing or stale.

        They are session data: a panel a file was saved with has none of them,
        and a geometry or seam change marks them. The first consumer that asks
        for a piece, a sample or a mesh builds them here, which is what makes a
        seam edit cheap and the work land where the data is needed.
        """
        if not self.need_sections and self.sections_by_edge:
            return
        self.need_sections = False
        if self.sketch is not None:
            # The stage is always rebuilt from one section per edge before it is
            # cloned: a cut read against sections that a previous cut or a seam
            # boundary already split would land on the wrong pieces, and this
            # panel's copy is only ever cloned from the curves as they are now.
            self.sketch.update()
        self.clone_sections()
        self.sample_all()
        self.calc_bbox()
        self.need_geo_update = True

    def clone_sections(self) -> None:
        """Take this panel's own copy of the Sketch's first section stage.

        Deep, head to tail: what a linking run cuts at seam boundaries is this
        copy, and those cuts must never reach the Sketch or another panel of the
        chain. Nothing is patched into a copy that already exists - a copy cut by
        an older seam graph is dropped and cloned again from the stage the Sketch
        has now.
        """
        sketch = self.sketch
        self.sections_by_edge = {}
        self.section_heads = {}
        self.key_of_edge = {}
        if sketch is None:
            return
        chains = [(None, sketch.edges)]
        chains.extend((index, line.edges)
                      for index, line in enumerate(sketch.internal_lines))
        for key, edges in chains:  # loop: the outline, then one chain per line
            is_loop = key is None or sketch.internal_lines[key].is_loop
            chain = []
            for index, edge in enumerate(edges):  # loop: one edge's raw pieces
                self.key_of_edge[edge.global_uuid] = (key, index)
                pieces = [Section.from_raw(raw) for raw in edge.raw_sections()]
                for piece in pieces:  # loop: one span per piece of this edge
                    piece.edge_key = (key, index)
                    piece.panel = self
                self.sections_by_edge[(key, index)] = pieces
                chain.extend(pieces)
            if not chain:
                continue
            for position, section in enumerate(chain):  # loop: one link per piece
                section.prev = chain[position - 1] if position else None
                section.next = chain[position + 1] if position + 1 < len(chain) else None
            if is_loop:
                chain[0].prev = chain[-1]
                chain[-1].next = chain[0]
            self.section_heads[key] = chain[0]

    def sections_for_edge(self, key, index) -> list:
        """This panel's pieces of one edge, in chain order."""
        self.ensure_sections()
        return self.sections_by_edge.get((key, index), [])

    def pieces_of(self, key) -> list:
        """This panel's pieces of one chain: the outline, or one internal line."""
        self.ensure_sections()
        count = (len(self.edges) if key is None
                 else len(self.internal_lines[key].edges))
        pieces = []
        for index in range(count):  # loop: one edge's pieces at a time
            pieces.extend(self.sections_for_edge(key, index))
        return pieces

    def sample_all(self) -> None:
        """Take this panel's samples from its own copy of the stage."""
        self.sample_points = {}
        self.sample_starts = {}
        self.sample_sizes = {}
        self.line_sizes = {}
        for index in range(len(self.edges)):  # loop: one outline edge per run
            self.sample_edge(None, index)
        for line_index in range(len(self.internal_lines)):  # loop: one line per run
            for index in range(len(self.internal_lines[line_index].edges)):
                self.sample_edge(line_index, index)

    def sample_edge(self, key, index) -> None:
        """Sample one chain edge's pieces at this panel's granularity.

        `key` is None for the outline and a line's index for one of its internal
        lines. The samples land on the panel (`self.sample_points`) and the
        segment count and the sample offsets on the panel's own pieces, so two
        panels of one chain can sample the same edge differently.
        """
        sections = self.sections_for_edge(key, index)
        if not sections:
            return
        edges = self.edges if key is None else self.internal_lines[key].edges
        edge = edges[index]
        granularity = max(float(self.granularity), 1e-6)
        min_g = granularity
        for section in sections:  # loop: one segment count per piece
            if section.seg == -1:
                section.seg = max(math.ceil(section.absolute_length() / granularity), 1)
            min_g = min(section.absolute_length() / section.seg, min_g)
        if len(sections) == 1:
            point_size = sections[0].seg + 1
            sections[0].start_point = 0
            points = self._resample_edge_curve(edge, point_size)
        else:
            point_size = max(math.ceil(float(edge.length or 0.0) / min_g), 1) + 1
            temp = self._resample_edge_curve(edge, point_size * 2)
            segments = []
            count = 0
            for section in sections:  # loop: one sample run per piece
                section.start_point = count
                count += section.seg
                segments.append([section.start_pos, section.seg])
            segments[-1][1] += 1
            points = resample_polyline(temp, segments, True)
        self.sample_points[(key, index)] = points

    @staticmethod
    def _resample_edge_curve(edge, point_size) -> np.ndarray:
        """`point_size` points at equal arc length along one edge's own curve."""
        point_size = max(int(point_size), 2)
        temp_points = edge.generate_render_points(max(point_size * 2, 8))
        return resample_polyline(temp_points, [(0, point_size)], True)

    def key_of(self, edge) -> tuple:
        """Where one of the Sketch's edges sits in this panel: (line or None, index).

        The table is part of this panel's copy of the stage, so the copy is asked
        for first: a caller that reaches here before a marked rebuild - the
        linking run is one, and it asks for the edge before it asks for a piece -
        would otherwise read a table that is empty or one edit old.
        """
        self.ensure_sections()
        return self.key_of_edge.get(edge.global_uuid, (None, None))

    # --------------------------------------------------------------- picking

    def pick_id(self, kind, element) -> int:
        """The id this panel draws one of its elements with in the pick pass.

        A Sketch element is on screen once per pattern of its chain, so the
        element's own identity cannot be what a pick reads back: the id belongs
        to the pair. It is generated here, kept for the session, and the pass
        records which panel and which element it stood for, so a pointer over
        one member's edge resolves to that member and not to its copy.
        """
        key = (kind, int(element.global_uuid))
        table = self.pick_ids
        identifier = table.get(key)
        if identifier is None:
            identifier = global_data.new_pick_id()
            table[key] = identifier
        return identifier

    def find_or_add_section(self, edge, pos):
        """The piece of one edge a position falls in, cutting this panel's copy.

        The linking run uses this: a seam boundary has to sit on a piece boundary
        before a walk can be read off. The cut is made on this panel's own pieces
        (`Section.split` keeps the chain, the linking table and the per-edge
        pieces in step), so it never reaches the Sketch or another panel.
        """
        eps = 1e-5
        key, index = self.key_of(edge)
        pieces = self.sections_for_edge(key, index)
        if not pieces:
            return None
        if pos >= 1 - eps:
            return pieces[-1].next
        for section in pieces:  # loop: one piece per walk step
            if pos < section.start_pos:
                continue
            if pos - section.start_pos < eps:
                return section
            if pos > section.end_pos + eps:
                # The position is past this piece: it sits further along the
                # edge. Splitting here would cut the piece with a fraction
                # beyond its own end and leave a piece that runs backwards.
                continue
            radio = (pos - section.start_pos) / (section.end_pos - section.start_pos)
            _, new_section = section.split(radio)
            return new_section
        return None

    def register_piece(self, section) -> None:
        """Put a piece a split produced into this panel's per-edge list.

        `Section.split` calls this, so a piece a linking run cut is in the list
        the panel samples as well as in the chain a sewing walk follows: a piece
        missing from the list would never be given a segment count, and the two
        sides of the seam would end up with different stitch counts.
        """
        key, index = section.edge_key
        pieces = self.sections_by_edge.get((key, index))
        if pieces is None or section in pieces:
            return
        lower = section.prev
        if lower in pieces:
            pieces.insert(pieces.index(lower) + 1, section)
        else:
            pieces.append(section)

    def boundary_section(self, edge, pos, reverse=False):
        """The piece a sewing walk starts on, or stops at, for a position.

        Read-only: the stitch walk reads its boundaries back from the seam's own
        parameters with this instead of trusting a stored pair, so a later split
        cannot leave it pointing at the wrong piece. It reads this panel's own
        pieces - the ones a linking run cut - and never changes them.

        `reverse` asks for the piece below the boundary, which is where a walk
        against the chain starts (and stops). A seam only has an exact boundary
        here once it has been linked, so a missing one is reported rather than
        silently walking a longer range.
        """
        eps = 1e-5
        key, index = self.key_of(edge)
        pieces = self.sections_for_edge(key, index)
        if not pieces:
            raise ValueError(f"edge {edge.get_index()} has no pieces on "
                             f"{self.name or '(unnamed)'}")
        if pos >= 1 - eps:
            # None on an open chain's last edge: nothing follows its last piece,
            # which is where a walk ends anyway.
            section = pieces[-1].next
        else:
            section = None
            for candidate in pieces:  # loop: one piece per walk step
                if abs(candidate.start_pos - pos) <= eps:
                    section = candidate
                    break
            if section is None:
                raise ValueError(
                    f"edge {edge.get_index()} of {self.name or '(unnamed)'} has no "
                    f"section boundary at {pos:.4f}: the sewing that ends there "
                    f"has not been linked")
        if reverse:
            section = pieces[-1] if section is None else section.prev
            if section is None:
                raise ValueError(
                    f"edge {edge.get_index()} has nothing before position "
                    f"{pos:.4f}, so a reversed sewing cannot start there")
        return section

    def gen_mesh_edge_points_and_sections(self):
        """The outline's samples and the panel's own pieces they came from.

        Each piece's `mesh_start_point` says where the edge's samples start in
        the array the mesh is built from, so the mesh indices a piece produces
        are read from the panel's own copy rather than from a shared stage.
        """
        sections = []
        points = self.get_geo_points_unique()
        start_point_final = 0
        for index, edge in enumerate(self.edges):  # loop: one outline edge per run
            edge_sections = self.sections_for_edge(None, index)
            sections.extend(edge_sections)
            for section in edge_sections:  # loop: one mesh offset per piece
                section.mesh_start_point = start_point_final
                section.continuous = True
                start_point_final += section.seg
        if start_point_final != len(points):
            raise Exception("start_point_final != len(points)", start_point_final, len(points))
        sections[-1].mesh_end_point = 0
        return points, sections

    def calc_mesh_edge_points(self):
        # The pieces are this panel's own copy of the stage; a consumer that got
        # here before a marked rebuild asked for a mesh, not for pieces.
        self.ensure_sections()
        # The linking run cuts this panel's pieces at seam boundaries after the
        # samples were taken (`Section.split` leaves the new pieces unsegmented),
        # so the samples are brought up to date with the pieces here, once per
        # mesh build.
        self.sample_all()
        edge_points, edge_sections = self.gen_mesh_edge_points_and_sections()
        secion_index_offset = len(edge_points)
        self.mesh_edge_point_outer_size = secion_index_offset
        edge_points = [edge_points]

        for line_index, il in enumerate(self.internal_lines):  # loop: one line per run
            il_edge_points, il_sections = self.gen_inside_points_and_sections(
                line_index, secion_index_offset)
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
        mapped = mesh_edge_index_map[edge_indices].astype(np.int32)
        # `deduplicate_points` merges samples that sit closer than the threshold,
        # so a segment whose ends were merged lands on `(i, i)`: it is not a
        # segment any more, and the engine refuses it by name instead of
        # sampling it. Dropping one compacts the list and, per curve, the counts
        # the engine checks against it - so the common case, where nothing was
        # merged away, keeps the array it already has.
        keep = mapped[:, 0] != mapped[:, 1]
        if keep.all():
            self.mesh_edge_point_indices = mapped
        else:
            sizes = [self.mesh_edge_point_outer_size,
                     *[self.line_sizes[index] for index in range(len(self.internal_lines))]]
            kept, offset = [], 0
            for index, size in enumerate(sizes):
                block = mapped[offset:offset + size]
                block = block[block[:, 0] != block[:, 1]]
                sizes[index] = len(block)
                kept.append(block)
                offset += size
            self.mesh_edge_point_outer_size = sizes[0]
            for line_index, size in enumerate(sizes[1:]):
                self.line_sizes[line_index] = size
            self.mesh_edge_point_indices = np.concatenate(kept).astype(np.int32)
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
        """Add one point to this pattern's Sketch and return its index.

        The geometry is the Sketch's, so one call writes once for every member
        of the instance chain that shares it.
        """
        index = self.require_sketch().add_vertex(position)
        self.calc_bbox()
        return index

    def add_edge(self, start_idx, end_idx, control1=None, control2=None, handle1_type="VECTOR",
                 handle2_type="VECTOR", update=True):
        """Add one edge to this pattern's Sketch."""
        edge = self.require_sketch().add_edge(start_idx, end_idx, control1, control2,
                                              handle1_type, handle2_type, update)
        self.calc_bbox()
        return edge

    def add_internal_line(self, segments, is_loop=False):
        """Add one internal line from a run of curve pieces.

        ``segments`` is a list of dicts with ``p0``, ``p1`` (pattern space, in
        millimetres), ``h1``, ``h2``, ``h1_type`` and ``h2_type``; consecutive
        pieces share their end point the way the internal line pen draws them.
        The control points become points of this pattern's Sketch, exactly as
        they do when the pen writes the line, so the line can be edited
        afterwards.
        """
        line = self.require_sketch().add_internal_line(segments, is_loop)
        self.mark_geometry_changed()
        return line

    def update_render_line(self):
        if not self.initialized:
            self.initialize()
            self.initialized = True

        if len(self.vertices) < 2:
            return []
        render_points = []
        for i in range(len(self.edges)):
            self.edges[i].update()
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

    def get_geo_points_unique(self) -> np.ndarray:
        """The outline's samples, one edge at a time, without the joined ends.

        The outline is a loop, so the first point of the next edge is the last
        point of this one: it is dropped, and the offsets recorded here are the
        ones the mesh index map is built from.
        """
        self.ensure_sections()
        edge_points = []
        start_point = 0
        for index in range(len(self.edges)):  # loop: one outline edge per run
            points = np.asarray(self.sample_points[(None, index)], dtype=np.float32)[:-1]
            if points.shape[0] < 1:
                edge = self.edges[index]
                console.warning(edge.vertex0.co, edge.handle1_type,
                                edge.vertex1.co, edge.handle2_type)
                raise Exception("points.shape[0] < 1")
            edge_points.append(points)
            self.sample_starts[(None, index)] = start_point
            self.sample_sizes[(None, index)] = len(points)
            start_point += points.shape[0]
        return np.concatenate(edge_points, dtype=np.float32)

    def write_geo_points(self) -> None:
        """Keep a copy of the boundary samples the mesh is about to be built from.

        Called right before the mesh is generated, from the points that mesh is
        generated from. The samples themselves are session data - they are taken
        again from the Sketch at this panel's granularity whenever they are
        needed - but a check that runs without opening the add-on can only read
        what was written to the file, so the panel's own shape is kept there.
        """
        self.geo_points.clear()
        points = self.mesh_edge_points
        if points is None:
            return
        for point in np.asarray(points, dtype=np.float32):  # loop: one RNA point per sample
            entry = self.geo_points.add()
            entry.co = (float(point[0]), float(point[1]))

    def gen_inside_points_and_sections(self, line_index, index_offset=0):
        """One line's samples that lie inside the outline, and their pieces.

        Pieces marked outside are dropped, and a piece that continues into the
        next one shares its end point. Both come from this panel's own copy of
        the stage, so the mesh a panel builds cannot be read off another panel's
        cuts.
        """
        pieces = [section for section in self.pieces_of(line_index)
                  if not section.outsize]
        if not pieces:
            self.line_sizes[line_index] = 0
            return np.zeros((0, 2), dtype=np.float32), []
        chunks = []
        start_point_final = index_offset
        self.line_sizes[line_index] = int(np.sum([section.seg for section in pieces]))
        for position, section in enumerate(pieces):  # loop: one piece per run
            samples = np.asarray(self.sample_points[section.edge_key], dtype=np.float32)
            begin = section.start_point
            if position < len(pieces) - 1 and section.next is pieces[position + 1]:
                # Continuous: the next piece starts on the shared point.
                points = samples[begin:begin + section.seg]
                section.continuous = True
            else:
                points = samples[begin:begin + section.seg + 1]
                section.continuous = False
            chunks.append(points)
            section.mesh_start_point = start_point_final
            start_point_final += len(points)
        if (self.internal_lines[line_index].is_loop
                and pieces[-1].next is pieces[0]):
            pieces[-1].mesh_end_point = index_offset
        return np.concatenate(chunks, dtype=np.float32), pieces

    def get_vertice_list(self):
        list_vertices = []
        for vertex in self.vertices:
            list_vertices.append(vertex.co)
        return list_vertices

    def calc_bbox(self):
        """The panel's bounding box, measured on the curves themselves.

        The draw points are the shape; the samples are one rendering of it, so a
        box that needed them would be missing before a mesh pass and would move
        with the granularity.
        """
        chunks = []
        for edge in self.sketch.all_edges() if self.sketch is not None else []:
            edge.update()
            points = edge.render_points
            if points is not None and len(points) > 0:
                chunks.append(np.asarray(points, dtype=np.float32))
        if not chunks:
            return
        points = np.concatenate(chunks)
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

    def generate_mesh(self, scale_data=None, force=False):
        """Build this panel's mesh from the samples it has.

        A panel whose samples did not move since its mesh was built keeps the
        mesh it has: calling this again with nothing marked is a no-op, which is
        what makes a repeated call - a repair pass, a redraw that asks for the
        mesh - cost nothing. `force` and `scale_data` are for a caller that
        wants the mesh written again whatever the flags say.
        """
        if (not force and scale_data is None and self.mesh_object is not None
                and not self.need_geo_update):
            return
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
        if self.mesh_error:
            # The sampler already refused this exact shape: asking again on every
            # update pass would only repeat the error until the outline changes.
            return
        start = time.time()
        try:
            if self.need_geo_update:
                self.calc_mesh_edge_points()
            self.write_geo_points()
            self.mesh_object = generate_pattern_mesh(self, granularity, self.mesh_object,
                                                     scale_data)
        except Exception as error:
            # The sampler refuses geometry it cannot triangulate - a panel thinner
            # than one sampling cell, samples that merged onto each other, a
            # section chain that does not add up. The panel is left invalid with
            # the reason kept, so the editor stays alive and a simulation will not
            # start on it, instead of the error escaping into an operator.
            self.mesh_error = str(error) or error.__class__.__name__
            self.validity_state = VALIDITY_INVALID
            console.warning(f"pattern {self.name or '(unnamed)'}: no mesh: {self.mesh_error}")
            return
        self.mesh_error = None
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

    def copy_pattern(self, as_instance=False, mirror=False, project=None, anchor=None):
        """Copy this panel and return the copy.

        The copy references the same Sketch: one Sketch per instance chain, so
        copying a panel costs no geometry. A mirror is expressed by the
        transform matrix and the mesh scale, so `mirror` only flips the copy's
        flag. Nothing links the two panels - they are one chain because they
        read one Sketch - and a copy that is to have a shape of its own is
        detached afterwards.
        """
        from .qianyi_project import get_unique_name

        if project is None:
            project = self.project
        new_pattern = project.add_pattern(sketch=self.sketch)
        new_pattern.name = get_unique_name(
            project.patterns, f"{self.name}_{'mirror' if mirror else 'instance'}")
        new_pattern.sketch = self.sketch
        new_pattern.anchor = self.anchor[:] if anchor is None else (float(anchor[0]),
                                                                   float(anchor[1]))
        new_pattern.rotation = self.rotation
        new_pattern.grain_dir = self.grain_dir
        new_pattern.collision_layer = self.collision_layer
        new_pattern.fabric_uuid = self.fabric_uuid
        new_pattern.granularity = self.granularity
        new_pattern.is_mirror = bool(self.is_mirror) ^ bool(mirror)
        new_pattern.initialize()
        new_pattern.mark_geometry_changed()
        new_pattern.generate_mesh()
        return new_pattern

    def detach(self) -> dict:
        """Leave this pattern's instance chain and give it a Sketch of its own.

        A chain shares one Sketch, so this is the only way two patterns of one
        origin come to hold different geometry. The Sketch this pattern had is
        copied in the state it is in; the members that stay linked are
        untouched. A pattern that is already alone in its chain has nothing to
        detach, which the report says.
        """
        sketch = self.sketch
        staying = [pattern.name for pattern in self.sketch_members()
                   if pattern.global_uuid != self.global_uuid]
        if not staying:
            return {"pattern": self.name, "sketch": None, "detached": False,
                    "staying": [], "reason": "it is already alone in its chain"}
        private = sketch.copy(owner=self) if sketch is not None else None
        self.sketch = private
        self.need_sewing_update = True
        return {"pattern": self.name,
                "sketch": private.name if private is not None else None,
                "detached": True, "staying": staying,
                "reason": "the copy now holds its own Sketch"}

    def sketch_members(self) -> list:
        """Every panel that reads this panel's Sketch, this one first.

        A chain is what shares a Sketch, so it is read from the project instead
        of being kept as a list of its own: a panel that names no Sketch is
        alone, and a panel that names one is with the panels that name it too.
        Only the drawing of a selection and a generator rebuild have any use for
        this - a length-1 answer is the common case and the honest one for a
        panel that was never copied.
        """
        members = [self]
        if self.sketch_uuid == -1:
            # A panel with no Sketch has no geometry, so there is nothing for a
            # copy to share and nothing to look for: it is alone.
            return members
        for candidate in self.project.patterns:  # loop: one comparison per panel
            if candidate.global_uuid == self.global_uuid:
                continue
            if candidate.sketch_uuid == self.sketch_uuid:
                members.append(candidate)
        return members


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
define_temp_prop(Pattern, "impacted", False)
define_temp_prop(Pattern, "mesh_edge_points", None)
define_temp_prop(Pattern, "mesh_edge_index_map", None)
define_temp_prop(Pattern, "mesh_point_indices", None)
# The triangles the last mesh build wrote, for the next build's attribute
# mapping: reading them back from Blender re-tessellates the old mesh first.
define_temp_prop(Pattern, "mesh_triangles", None)
define_temp_prop(Pattern, "mesh_edge_point_outer_size", -1)
# The panel's own copy of the Sketch's first section stage, and the samples taken
# from it. Session data: it is rebuilt from the Sketch whenever this panel asks
# for a mesh, and a reload starts with none of it.
define_temp_prop(Pattern, "sections_by_edge", dict)
define_temp_prop(Pattern, "section_heads", dict)
define_temp_prop(Pattern, "key_of_edge", dict)
# The ids this panel draws its own elements with in the pick pass, one per
# (kind, element). Session data: a pick only ever reads what the pass left.
define_temp_prop(Pattern, "pick_ids", dict)
define_temp_prop(Pattern, "sample_points", dict)
define_temp_prop(Pattern, "sample_starts", dict)
define_temp_prop(Pattern, "sample_sizes", dict)
define_temp_prop(Pattern, "line_sizes", dict)
# Whether this panel's own copy of the Sketch's stage and its samples are up to
# date. Session data, and true at the start of a session: nothing is stored.
define_temp_prop(Pattern, "need_sections", True)
# Outline validity. A temp prop on purpose: it is a cache of an engine answer,
# so it is never written to the file and a reopened scene starts as unknown.
define_temp_prop(Pattern, "validity_state", VALIDITY_UNKNOWN)
define_temp_prop(Pattern, "invalid_point", None)
# Why the last mesh attempt was refused, or None. Kept as text so the panel can
# show what the engine said instead of only that something is wrong.
define_temp_prop(Pattern, "mesh_error", None)

register, unregister = register_classes_factory((Pattern,))
