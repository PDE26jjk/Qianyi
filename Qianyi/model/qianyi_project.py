import bpy
import numpy as np
import random
from bpy.utils import register_classes_factory

from ..utilities.console import console
from .. import global_data
from .pattern import Pattern

from .fabric import Fabric
from .generator import (PatternGenerator, generator_of_pattern, instance_chain,
                        refresh_generators)
from .model_data import ModelData, define_temp_prop
from .sewing import Sewing, calc_sewing_sections
from ..declarations import Panels


def library_category_items(self=None, context=None):
    """Categories offered by the panel library, evaluated when the UI asks."""
    from ..panellib import registry

    items = [("ALL", "All", "Every panel component")]
    try:
        categories = sorted({info.category for info in registry.infos()})
    except Exception:
        categories = []
    items.extend((category.upper(), category, "") for category in categories)
    return items


class UuidType(bpy.types.PropertyGroup):
    uuid: bpy.props.IntProperty(default=-1)


def get_unique_name(collection, base_name):
    if base_name not in collection:
        return base_name

    i = 1
    while f"{base_name}.{i:03d}" in collection:
        i += 1
    return f"{base_name}.{i:03d}"


def normalize_sewing_color(color):
    """The RGB a sewing is drawn with.

    A caller (a script, an importer) can pass its own (r, g, b) or (r, g, b, a)
    tuple; without one the sewing gets a random but saturated color, so adjacent
    chains are told apart instead of every one of them being white.
    """
    if color is None:
        import colorsys

        r, g, b = colorsys.hsv_to_rgb(random.random(), 0.7, 1.0)
        return (r, g, b)
    values = [float(value) for value in color]
    if len(values) < 3:
        raise ValueError(f"sewing color needs at least three components, got {color!r}")
    return tuple(max(0.0, min(1.0, value)) for value in values[:3])


def edge_click_fraction(edge, point):
    """Where along an edge a point sits: 0.0 at its start, 1.0 at its end."""
    points = edge.render_points
    if points is None or len(points) < 2:
        return 0.0
    delta_x = points[:, 0] - float(point[0])
    delta_y = points[:, 1] - float(point[1])
    return float(np.argmin(delta_x * delta_x + delta_y * delta_y)) / (len(points) - 1)


def sewing_half_directions(edge1, point1, edge2, point2):
    """``(pos1, pos2, reverse)`` for both halves of a one-to-one sewing.

    Each click only says which of its edge's two ends is nearer. When both
    clicks are near the same end - both first or both second - both halves run
    from their edge's first point to its second and nothing is flipped. When
    the clicks are near different ends the second half is flipped: it runs from
    its second point back to its first.

    `reverse` is the flip: False follows the edge's vertex order, True walks
    against it. A flipped half is also the one that has to leave its edge
    through the second point, otherwise the section walk would go the long way
    round the pattern.
    """
    first_of_edge1 = edge_click_fraction(edge1, point1) < 0.5
    first_of_edge2 = edge_click_fraction(edge2, point2) < 0.5
    if first_of_edge1 == first_of_edge2:
        return (0.0, 1.0, False), (0.0, 1.0, False)
    return (0.0, 1.0, False), (1.0, 0.0, True)


def edge_point_at(edge, position):
    """The edge end a half-sewing position refers to."""
    points = edge.render_points
    if points is None or len(points) < 2:
        return (0.0, 0.0)
    return points[0] if position < 0.5 else points[-1]


class QianyiProject(bpy.types.NodeTree, ModelData):
    """ Qianyi Project for editor, a NodeTree"""
    bl_label = "Qianyi Project"
    bl_icon = 'FILE_SCRIPT'
    bl_idname = Panels.QianyiNodeTree

    patterns: bpy.props.CollectionProperty(
        type=Pattern,
        name="patterns",
        description="The patterns of this project",
    )

    sewings: bpy.props.CollectionProperty(
        type=Sewing,
        name="sewings",
        description="The sewings of this project",
    )
    fabrics: bpy.props.CollectionProperty(
        type=Fabric,
        name="fabrics",
        description="The fabrics of this project",
    )
    generators: bpy.props.CollectionProperty(
        type=PatternGenerator,
        name="generators",
        description="Parametric panel generators of this project",
    )

    active_pattern_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active Pattern",
        description="The project editing",
        # update=update_active_pattern_index,
    )
    active_fabric_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active fabric",
        description="The project editing",
        # update=update_active_fabric_index,
    )
    active_generator_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active generator",
        description="The generator shown in the library panel",
    )
    library_filter: bpy.props.StringProperty(
        name="Search",
        default="",
        description="Filter the panel library by name, category or description",
    )
    library_category: bpy.props.EnumProperty(
        name="Category",
        items=library_category_items,
        description="Show only components of this category",
    )
    library_component_id: bpy.props.StringProperty(
        name="Selected component",
        default="",
        description="Component shown in the library's detail area",
    )

    # Silhouette guide: objects projected into the pattern window as an
    # alignment background. Display only - nothing here is meshed, simulated or
    # written into the engine payload.
    show_silhouette: bpy.props.BoolProperty(
        name="Show Silhouette",
        description="Draw the silhouette of the collection below behind the "
                    "panels of the pattern editor",
        default=False,
    )
    silhouette_collection: bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name="Objects",
        description="Collection projected into the pattern window as an "
                    "alignment background (typically the body)",
    )
    silhouette_axis: bpy.props.EnumProperty(
        name="View",
        description="World axis the silhouette is projected along",
        items=[
            ('X', "Side (X)", "Project along X, so the body is seen from its side"),
            ('Y', "Front (Y)", "Project along Y, so the body is seen from the front"),
            ('Z', "Top (Z)", "Project along Z, so the body is seen from above"),
        ],
        default='Y',
    )
    silhouette_offset: bpy.props.FloatVectorProperty(
        name="Offset",
        description="Move the silhouette within the pattern window, in millimetres",
        size=2,
        default=(0.0, 0.0),
    )
    silhouette_color: bpy.props.FloatVectorProperty(
        name="Color",
        description="Colour the silhouette is drawn with",
        subtype='COLOR',
        size=3,
        default=(0.35, 0.35, 0.40),
        min=0.0,
        max=1.0,
    )
    silhouette_opacity: bpy.props.FloatProperty(
        name="Fill Opacity",
        description="Opacity of the filled silhouette",
        default=0.25,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )
    silhouette_show_mesh: bpy.props.BoolProperty(
        name="Mesh",
        description="Also draw the projected mesh edges over the fill",
        default=True,
    )
    silhouette_mesh_opacity: bpy.props.FloatProperty(
        name="Mesh Opacity",
        description="Opacity of the projected mesh edges",
        default=0.35,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )

    index: bpy.props.IntProperty(
        default=-1,
        description="The index of this node tree in the node tree list",
        name="Index",
    )

    selected_patterns: bpy.props.CollectionProperty(type=UuidType)
    selected_vertices: bpy.props.CollectionProperty(type=UuidType)
    selected_edges: bpy.props.CollectionProperty(type=UuidType)
    selected_sewings: bpy.props.CollectionProperty(type=UuidType)

    # def update(self):
    #     pass
    #
    def calc_all_sewings_sections(self):
        self.refresh_collection_uuid(self.sewings)
        # Start every recompute from fresh sections.
        #
        # The link id lives on the Section object, while the list those ids
        # index into (`Section.link_sections`) is cleared at the start of
        # calc_sewing_sections. Linking sections that still carry an id from
        # the previous run therefore fails: two sections that happen to share
        # an id raise "Sewing overlap!!!" even though the sewing is valid, and
        # different ids walk into the list that was just emptied. It also needs
        # the edge geometry (length, sampled points, sections) built, which a
        # freshly opened file or a just created pattern does not have yet -
        # that used to fail inside with a NoneType error. The simulation path
        # does the same three steps (recreate_sections, forced_update,
        # calc_sewings_sections); this is that sequence for the sewings the
        # editor is about to link.
        for pattern in self.sewing_patterns():
            pattern.recreate_sections()
            pattern.forced_update()
        calc_sewing_sections(self.sewings)
        for p in self.patterns:
            p.need_sewing_update = False

    def sewing_patterns(self):
        """Every pattern the current sewings touch, each one once."""
        patterns = []
        seen = set()
        for sewing in self.sewings:
            for pattern in self.sewing_patterns_of(sewing):
                if pattern.global_uuid in seen:
                    continue
                seen.add(pattern.global_uuid)
                patterns.append(pattern)
        return patterns

    def calc_sewings_sections(self, sewings):
        calc_sewing_sections(sewings)

    def get_default_fabric(self):
        if len(self.fabrics) < 1:
            self.fabrics.add()
            self.fabrics[0].name = "Default Fabric"
        return self.fabrics[0]

    def clear_temp_data(self):
        self.initialized = False

    def update_all(self, forced=False):
        if not self.initialized or forced:
            for p in self.patterns:
                f = p.fabric
            self.initialized = True
        # for p in self.patterns:
        #     p.forced_update()

    def get_selected_objects_by_mode(self, mode, submode=None):
        selected_objects = []
        if mode == "PATTERN":
            for uuid in self.selected_patterns:
                selected_objects.append(global_data.get_obj_by_uuid(uuid.uuid, check_uuid=True))
        elif mode == "EDGE":
            if submode == "EDGE_VERTEX":
                for uuid in self.selected_edges:
                    selected_objects.append(global_data.get_obj_by_uuid(uuid.uuid, check_uuid=True))
                for uuid in self.selected_vertices:
                    selected_objects.append(global_data.get_obj_by_uuid(uuid.uuid, check_uuid=True))
        elif mode == "SEWING":
            for uuid in self.selected_sewings:
                selected_objects.append(global_data.get_obj_by_uuid(uuid.uuid, check_uuid=True))
        return selected_objects

    def clear_selected_objects_by_mode(self, mode):
        if mode == "PATTERN":
            self.selected_patterns.clear()
        elif mode == "EDGE":
            self.selected_edges.clear()
            self.selected_vertices.clear()
        elif mode == "SEWING":
            self.selected_sewings.clear()

    def add_sewing(self, side1_line1, side1_pos1, side1_line2, side1_pos2, side1_reverse,
                   side2_line1, side2_pos1, side2_line2, side2_pos2, side2_reverse, update=True,
                   color=None):
        sw = self.sewings.add()
        sw.side1.update_data(side1_line1, side1_pos1, side1_line2, side1_pos2, side1_reverse)
        sw.side2.update_data(side2_line1, side2_pos1, side2_line2, side2_pos2, side2_reverse)
        sw.color = normalize_sewing_color(color)
        if update:
            try:
                # calc_all_sewings_sections rebuilds the edge geometry of every
                # pattern a sewing touches first; see ensure_sewing_geometry.
                self.calc_all_sewings_sections()
                sw.update()
            except Exception as e:
                console.warning("Failed to add sewing: ", e)
                self.sewings.remove(len(self.sewings) - 1)
                # Keep the reason: the add-sewing operator used to show
                # "sewing overlap!" for every failure, which hid a missing
                # section, a missing edge length and a real overlap behind the
                # same message.
                self.last_sewing_error = str(e)
                return None
        self.refresh_collection_uuid(self.sewings)
        sw.pattern1.need_sewing_update = True
        sw.pattern2.need_sewing_update = True
        return sw

    @staticmethod
    def sewing_patterns_of(sewing):
        """The patterns a sewing joins, in a stable order."""
        patterns = []
        for side in (sewing.side1, sewing.side2):
            line = side.line1
            pattern = line.pattern if line is not None else None
            if pattern is not None and pattern not in patterns:
                patterns.append(pattern)
        return patterns

    def add_sewing1to1(self, edge1, edge2, reverse=False, color=None):
        first_half = (0.0, 1.0, False)
        second_half = (0.0, 1.0, False) if not reverse else (1.0, 0.0, True)
        return self.add_sewing(edge1, first_half[0], edge1, first_half[1], first_half[2],
                               edge2, second_half[0], edge2, second_half[1], second_half[2],
                               color=color)

    def add_sewing1to1_from_points(self, edge1, point1, edge2, point2, color=None):
        """One-to-one sewing whose direction follows where the edges were clicked.

        `point1` / `point2` are the click positions in the pattern space of
        their edge. Clicks near the same end of both edges keep the original
        pairing; clicks near different ends flip the second half - which is the
        only way this editor can express the two stitch directions.
        """
        first_half, second_half = sewing_half_directions(edge1, point1, edge2, point2)
        return self.add_sewing(edge1, first_half[0], edge1, first_half[1], first_half[2],
                               edge2, second_half[0], edge2, second_half[1], second_half[2],
                               color=color)

    def setup_sewings_for_simulation(self):
        # self.calc_all_sewings_sections()
        # recalculate all sewings if needed.
        for pattern in self.patterns:
            if pattern.need_sewing_update:
                connected_patterns, involved_sewings = pattern.get_connected_patterns_and_sewings()
                for p in connected_patterns:
                    p.recreate_sections()
                    p.forced_update()
                self.calc_sewings_sections(involved_sewings)
                for p in connected_patterns:
                    p.need_sewing_update = False
                    p.generate_mesh()

        sewings = [sewing.get_stitch_data() for sewing in self.sewings]
        return sewings

    def update_edge_finder(self):
        edge_points = []
        edge_point_sizes = []
        matrices = []
        for p in self.patterns:
            ps = p.get_geo_points_unique()
            edge_points.append(ps)
            edge_point_sizes.append(len(ps))
            matrices.append(np.array(p.calc_matrix()))
        edge_points = np.concatenate(edge_points, dtype=np.float32)
        # console.info('edge_point_sizes', edge_point_sizes)
        edge_point_sizes = np.array(edge_point_sizes, dtype=np.int32)
        matrices = np.concatenate(matrices, dtype=np.float32)
        # console.info('matrices', matrices)
        from Qianyi_DP import pattern_helper
        pattern_helper.update_edges(edge_points, edge_point_sizes, matrices)
        self.edge_points = edge_points
        self.edge_point_sizes = np.cumsum(edge_point_sizes)

    def clear_edge_finder(self):
        self.edge_points = None

    def find_nearest_point_on_edge(self, query_point):
        if self.edge_points is None:
            self.update_edge_finder()
        from Qianyi_DP import pattern_helper
        res = pattern_helper.find_nearest_edge(query_point)
        # console.info('res', res)
        # console.info('self.edge_point_sizes', self.edge_point_sizes)
        index = res['res_index']
        weight = res['res_weight']
        n = np.searchsorted(self.edge_point_sizes, index, side='left')
        next_index = index + 1
        if self.edge_point_sizes[n] - 1 == index:
            next_index = self.edge_point_sizes[n - 1] if n > 0 else 0
        if self.edge_point_sizes[n] == index:
            n += 1
        pattern_point_offset = 0 if n == 0 else self.edge_point_sizes[n - 1]
        self.edge_point_offset = index - pattern_point_offset

        self.nearest_pattern = n
        # console.info('n', n, self.edge_point_sizes[n])
        # console.info('next_index', next_index)
        self.nearest_point = self.edge_points[index] * (1 - weight) + self.edge_points[next_index] * weight
        self.query_point = query_point
        # console.warning('self.nearest_point', self.nearest_point)

    def get_nearest_point_data(self):
        pattern: Pattern = self.patterns[self.nearest_pattern]
        point_offsets = [edge.start_point for edge in pattern.edges]
        edge_index = np.searchsorted(point_offsets, self.edge_point_offset, side='right') - 1
        edge = pattern.edges[edge_index]
        point_index = self.edge_point_offset - edge.start_point
        if point_index >= len(edge.geo_points_temp) - 1:
            raise ValueError("Point index out of range!!!", point_index, len(edge.geo_points_temp))
        point_start = edge.geo_points_temp[point_index]
        pts = edge.geo_points_temp[:point_index + 1]
        length = (np.sum(np.linalg.norm(pts[1:] - pts[:-1], axis=1)) +
                  np.linalg.norm(self.nearest_point - point_start))
        t = length / edge.length
        return pattern, edge, self.nearest_point, t

    def add_pattern(self):
        p = self.patterns.add()
        self.refresh_collection_uuid(self.patterns)
        name = f"pattern_{len(self.patterns):03d}"
        p.name = get_unique_name(self.patterns, name)
        return p

    def remove_impacted_sewings(self):
        """Drop the sewings flagged as impacted; returns how many went.

        An editor deletes an element but flags every sewing that used it, and a
        deleted element leaves its uuid in the in-memory map still pointing at a
        wrapper that now reads a different uuid - so any lookup of it raises.
        Everything that walks all sewings has to run after the sewings that lost
        a line are gone; `forced_update` walks them through
        `get_connected_patterns_and_sewings`.
        """
        indexes = [sewing.get_index() for sewing in self.sewings if sewing.impacted]
        for index in sorted(indexes, reverse=True):
            self.sewings.remove(index)
        if indexes:
            self.refresh_collection_uuid(self.sewings)
            self.selected_sewings.clear()
        return len(indexes)

    def _unlink_pattern_from_instance_list(self, pattern_to_del):
        uuid_to_del = pattern_to_del.global_uuid
        if uuid_to_del == -1:
            return

        next_uuid = pattern_to_del.instance_next_uuid
        if next_uuid == -1:
            return

        prev_node = None
        current_uuid = next_uuid
        max_tries = len(self.patterns) + 1

        while max_tries > 0:
            current_node = global_data.get_obj_by_uuid(current_uuid)
            if current_node is None:
                break

            if current_node.instance_next_uuid == uuid_to_del:
                prev_node = current_node
                break

            current_uuid = current_node.instance_next_uuid
            # 如果转了一圈回到起点还没找到，说明逻辑异常，退出防死循环
            if current_uuid == next_uuid:
                break
            max_tries -= 1

        if prev_node:
            # 核心断开逻辑：前驱节点跨过当前节点，直接指向后继节点
            prev_node.instance_next_uuid = pattern_to_del.instance_next_uuid

            # 如果链表删到只剩一个节点(即前驱节点的下一个是自己)，恢复初始状态 -1
            if prev_node.instance_next_uuid == prev_node.global_uuid:
                prev_node.instance_next_uuid = -1

        pattern_to_del.instance_next_uuid = -1

    def remove_patterns(self, patterns_to_delete, expand_groups=True):
        if expand_groups:
            patterns_to_delete = self._expand_pattern_groups(patterns_to_delete)
        for p in patterns_to_delete:
            self._unlink_pattern_from_instance_list(p)

        selected_patterns_uuid = [p.global_uuid for p in patterns_to_delete]
        del_idx_list = []
        for sw in self.sewings:
            if (sw.side1.line1.pattern.global_uuid in selected_patterns_uuid or
                    sw.side2.line1.pattern.global_uuid in selected_patterns_uuid):
                del_idx_list.append(sw.get_index())

        for i in sorted(del_idx_list, reverse=True):
            self.sewings.remove(i)
        self.selected_sewings.clear()
        self.refresh_collection_uuid(self.sewings)

        del_idx_list = []
        for p in patterns_to_delete:
            if p.global_uuid != -1:
                obj = global_data.get_obj_by_uuid(p.global_uuid, check_uuid=False)
                if hasattr(obj, 'mesh_object') and obj.mesh_object is not None:
                    bpy.data.objects.remove(obj.mesh_object)
                if obj is not None:
                    del_idx_list.append(obj.get_index())
                else:
                    console.error('cannot find pattern', p.global_uuid)
        for i in sorted(del_idx_list, reverse=True):
            self.patterns.remove(i)

        self.refresh_patterns()

    def _expand_pattern_groups(self, patterns_to_delete):
        """Deleting one panel of a generator deletes the whole group.

        A generated panel is not a standalone object: its siblings and the
        generator that produced them are one unit, so removing any of them
        removes the unit.
        """
        expanded = list(patterns_to_delete)
        seen = {p.global_uuid for p in expanded}
        generators_to_remove = []
        for pattern in patterns_to_delete:
            generator = generator_of_pattern(self, pattern)
            if generator is None or generator in generators_to_remove:
                continue
            generators_to_remove.append(generator)
            for output in generator.outputs:
                if output.pattern_uuid == -1:
                    continue
                sibling = global_data.get_obj_by_uuid(output.pattern_uuid, check_uuid=False)
                # A copy of a generated panel belongs to the same group.
                for member in instance_chain(sibling):
                    if member.global_uuid not in seen:
                        expanded.append(member)
                        seen.add(member.global_uuid)

        if generators_to_remove:
            indices = sorted((generator.get_index() for generator in generators_to_remove
                              if generator.get_index() is not None), reverse=True)
            for index in indices:
                if 0 <= index < len(self.generators):
                    self.generators.remove(index)
            refresh_generators(self)
            self.active_generator_index = max(
                0, min(self.active_generator_index, len(self.generators) - 1))
        return expanded

    def refresh_patterns(self):
        self.refresh_collection_uuid(self.patterns)
        for p in self.patterns:
            p.clear_temp_data()
        refresh_generators(self)


define_temp_prop(QianyiProject, "initialized", False)
define_temp_prop(QianyiProject, "edge_points", None)
define_temp_prop(QianyiProject, "edge_point_sizes", None)
define_temp_prop(QianyiProject, "nearest_point", None)
define_temp_prop(QianyiProject, "query_point", None)
define_temp_prop(QianyiProject, "nearest_pattern", None)
define_temp_prop(QianyiProject, "edge_point_offset", None)
define_temp_prop(QianyiProject, "selected_sewing_edge1", None)
define_temp_prop(QianyiProject, "selected_sewing_point1", None)
define_temp_prop(QianyiProject, "last_sewing_error", "")

register, unregister = register_classes_factory((UuidType, QianyiProject))
