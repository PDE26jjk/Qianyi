import math
from typing import List

import numpy as np
from bpy.props import EnumProperty, FloatProperty, PointerProperty, IntProperty, CollectionProperty, \
    FloatVectorProperty, BoolProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .internal_line import InternalLine
from ..utilities.console import console
from ..utilities.geometric_operation import split_polyline
from .. import global_data
from .model_data import ModelData, define_temp_prop, Selectable
from .geometry import Edge2D, Section


# LineType = [
#     ("EDGE", "Edge", "", 1),
#     ("INTERNAL_LINE", "InternalLine", "", 2),
# ]


class SewingOneSide(PropertyGroup, ModelData, Selectable):
    line1_uuid: IntProperty(name="line1_id")
    pos1: FloatProperty(name="position1", min=0.0, max=1.0, default=0.0)
    line2_uuid: IntProperty(name="line2_id")
    pos2: FloatProperty(name="position2", min=0.0, max=1.0, default=1.0)
    reverse: BoolProperty(name="reverse", default=False)  # False for ccw, True for not ccw

    def update_data(self, line1, pos1, line2, pos2, reverse):
        self.line1_uuid = line1.global_uuid
        self.pos1 = pos1
        self.line2_uuid = line2.global_uuid
        self.pos2 = pos2
        self.reverse = reverse

    @property
    def line1(self):
        # During a panel rebuild the edge collection is rewritten before the
        # sewings are remapped, so this lookup can transiently point at a
        # shifted wrapper. Return None instead of raising.
        return global_data.get_obj_by_uuid(self.line1_uuid, check_uuid=False)

    @property
    def line2(self):
        return global_data.get_obj_by_uuid(self.line2_uuid, check_uuid=False)


define_temp_prop(SewingOneSide, "sewing", None)


class Sewing(PropertyGroup, ModelData, Selectable):
    sides: CollectionProperty(type=SewingOneSide)
    color: FloatVectorProperty(
        name="color",
        description="The color of the Sewing",
        subtype="COLOR",
        default=(1., 1, 1),
        size=3,
    )

    def get_side1(self):
        if len(self.sides) < 1:
            self.sides.add()
        return self.sides[0]

    def get_side2(self):
        if len(self.sides) < 2:
            if len(self.sides) < 1:
                self.sides.add()
            self.sides.add()
        return self.sides[1]

    @property
    def pattern1(self):
        line = self.side1.line1
        return line.pattern if line is not None else None

    @property
    def pattern2(self):
        line = self.side2.line1
        return line.pattern if line is not None else None

    @property
    def side1(self):
        return self.get_side1()

    @property
    def side2(self):
        return self.get_side2()

    def clear_temp_data(self):
        self.need_render_update = True

    def update(self):
        if not self.need_render_update:
            return
        self.need_render_update = False
        if global_data.renderers_enabled and self.renderer is None:
            from ..gizmos.sewing_renderer import SewingRenderer
            self.renderer = SewingRenderer(self)

        render_points1 = calc_sewing_side_render_points(self.side1)
        render_points2 = calc_sewing_side_render_points(self.side2)

        self.side1.sewing = self
        self.side2.sewing = self
        if global_data.renderers_enabled:
            self.renderer.update_batch_edge(render_points1, render_points2)

    def get_stitch_data(self):
        ss1 = self.side1
        ss2 = self.side2
        pattern1 = ss1.line1.pattern
        pattern2 = ss2.line1.pattern
        for pattern in (pattern1, pattern2):
            if pattern.mesh_object is None:
                # A crossing outline is not meshed at all, so a sewing that
                # ends on it has no vertices to pair. Say that instead of
                # failing on a None object further down.
                raise ValueError(f"pattern {pattern.name or '(unnamed)'} has no mesh "
                                 f"(its outline is invalid?)")
        if pattern1.need_geo_update:
            pattern1.calc_mesh_edge_points()
        if pattern2.need_geo_update:
            pattern2.calc_mesh_edge_points()
        patterns = (pattern1.mesh_object.qmyi_simulation_props.simulation_index,
                    pattern2.mesh_object.qmyi_simulation_props.simulation_index)

        start1, end1 = self.sections1
        start2, end2 = self.sections2
        stitches1 = get_stitches_by_sections(start1, end1, ss1.reverse)
        stitches2 = get_stitches_by_sections(start2, end2, ss2.reverse)
        stitches = np.column_stack((stitches1, stitches2))

        return {'patterns': patterns, 'stitches': stitches, 'angle': 0.}


define_temp_prop(Sewing, "need_render_update", True)
define_temp_prop(Sewing, "renderer", None)
define_temp_prop(Sewing, "sections1", lambda: [None, None])
define_temp_prop(Sewing, "sections2", lambda: [None, None])
define_temp_prop(Sewing, "impacted", False)


def get_stitches_by_sections(start_section, end_section, reverse):
    sec = start_section
    pattern = sec.edge.pattern
    start = False
    is_loop = sec is end_section
    stitches_list = []
    max_sec = 10000
    while (sec is not end_section or not start) and max_sec > 0:
        point_size = sec.seg
        next = sec.prev if reverse else sec.next
        if next is end_section and not is_loop:
            point_size += 1

        stitches_index = pattern.mesh_edge_index_map[sec.mesh_start_point: sec.mesh_start_point + point_size]
        if point_size - len(stitches_index) == 1:
            stitches_index = np.append(stitches_index, pattern.mesh_edge_index_map[0])
        if point_size != len(stitches_index):
            raise IndexError("Something went wrong")
        if sec.mesh_end_point != -1:
            stitches_index[-1] = pattern.mesh_edge_index_map[sec.mesh_end_point]
        stitches_list.append(stitches_index)
        sec = next
        max_sec -= 1
        start = True
    if reverse:
        stitches_list.reverse()
    stitches = np.concatenate(stitches_list)
    if reverse:
        stitches = stitches[::-1]
    return stitches


def calc_sewing_side_sections(ss, sections_start_end, reverse=False):
    max_sec = 10000
    sections: List[Section] = []
    sec_start = ss.line1.find_or_add_section(ss.pos1)
    sec_end = ss.line2.find_or_add_section(ss.pos2)
    assert sec_start is not None, "sec_start is None!!!"
    if reverse:
        sec_start, sec_end = sec_start.prev, sec_end.prev
    sections_start_end[0] = sec_start
    sections_start_end[1] = sec_end
    sec = sec_start
    while sec != sec_end and max_sec > 0:
        sections.append(sec)
        sec = sec.next if not reverse else sec.prev
        max_sec -= 1
    if max_sec == 0:
        raise ValueError("sewing side in different pattern!!")

    lengths = np.fromiter((obj.absolute_length() for obj in sections), dtype=np.float64)
    scans = np.cumsum(lengths)
    lengths /= scans[-1]
    scans /= scans[-1]

    return sections, lengths, scans


# Create sections and calculate intersections before call it.
def calc_sewing_sections(sewings):
    link_sections = Section.link_sections
    link_sections.clear()

    # Split and link sections by sewings.
    blur_factor = 0.05
    for sewing in sewings:
        ss1, ss2 = sewing.side1, sewing.side2
        sections1, lengths1, scans1 = calc_sewing_side_sections(ss1, sewing.sections1, ss1.reverse)
        sections2, lengths2, scans2 = calc_sewing_side_sections(ss2, sewing.sections2, ss2.reverse)
        i = j = 0
        n1, n2 = len(sections1), len(sections2)
        reverse = ss1.reverse ^ ss2.reverse
        while i < n1 and j < n2:
            if abs(scans1[i] - scans2[j]) <= blur_factor:
                sections1[i].link_to(sections2[j])
                i += 1
                j += 1
                continue
            if scans1[i] <= scans2[j]:
                cut_length = scans1[i] - (scans2[j] - lengths2[j])
                radio = cut_length / lengths2[j]
                s1, s2 = sections2[j].split(radio, reverse)
                sections1[i].link_to(s1)
                sections2[j] = s2
                lengths2[j] -= cut_length
                i += 1
            else:
                cut_length = scans2[j] - (scans1[i] - lengths1[i])
                radio = cut_length / lengths1[i]
                s1, s2 = sections1[i].split(radio)
                sections2[j].link_to(s1, reverse)
                sections1[i] = s2
                lengths1[i] -= cut_length
                j += 1

    # Linked sections should have same segments.
    for i, dir_sections in enumerate(link_sections):
        if dir_sections:
            sections = [d.section for d in dir_sections]
            max_seg = -1
            for sec in sections:
                seg = max(math.ceil(sec.absolute_length() / sec.edge.pattern.granularity), 1)
                max_seg = max(max_seg, seg)
            for sec in sections:
                if sec.seg != max_seg:
                    sec.seg = max_seg
                    sec.edge.need_update_points = True
                    sec.edge.pattern.need_geo_update = True
            # console.warning(i, sections, max_seg)


def calc_sewing_side_edges_index(ss, parent):
    e1_index = e2_index = -1
    for i, e in enumerate(parent.edges):
        if e.global_uuid == ss.line1_uuid:
            e1_index = i
        if e.global_uuid == ss.line2_uuid:
            e2_index = i
        if e1_index != -1 and e2_index != -1:
            break
    if e1_index == -1 or e2_index == -1:
        raise ValueError("sewing side in different pattern!!", ss.line1.pattern, ss.line2.pattern)
    return e1_index, e2_index


def calc_sewing_side_edges(ss):
    # p = ss.line1.pattern
    parent = ss.line1.get_parent()
    e1_i, e2_i = calc_sewing_side_edges_index(ss, parent)
    e_i = e1_i
    edges: List[Edge2D] = [parent.edges[e_i]]
    crazy_loop = e1_i == e2_i and (ss.pos1 > ss.pos2) ^ ss.reverse
    # console.info(crazy_loop,(ss.pos1 > ss.pos2) , ss.reverse)
    step = -1 if ss.reverse else 1
    il = parent if isinstance(parent, InternalLine) else None
    if il:
        pass  # ?

    if crazy_loop:
        e_i = (e_i + step) % len(parent.edges)
        edges.append(parent.edges[e1_i])
    while e_i != e2_i:
        e_i = (e_i + step) % len(parent.edges)
        edges.append(parent.edges[e_i])
    return edges


def calc_sewing_side_render_points(ss):
    edges = calc_sewing_side_edges(ss)
    # console.info(edges)

    if len(edges) == 1:
        pos1, pos2 = ss.pos1, ss.pos2
        if pos1 > pos2:
            pos1, pos2 = pos2, pos1
        new_percent = (pos2 - pos1) / (1.0 - pos1)
        _, render_points = split_polyline(edges[0].render_points, pos1)
        render_points, _ = split_polyline(render_points, new_percent)
        render_points = render_points.astype(np.float32)
        # console.info(render_points)
    else:
        if not ss.reverse:
            _, start_chain = split_polyline(edges[0].render_points, ss.pos1)
            end_chain, _ = split_polyline(edges[-1].render_points, ss.pos2)
        else:
            start_chain, _ = split_polyline(edges[0].render_points, ss.pos1)
            _, end_chain = split_polyline(edges[-1].render_points, ss.pos2)

        render_points = list(start_chain)
        for i in range(1, len(edges) - 1):
            render_points.append(edges[i].render_points)
        render_points.append(end_chain)
        render_points = np.concatenate(render_points, dtype=np.float32)
    if ss.reverse:
        # render_points = render_points[::-1]
        render_points = np.flip(render_points, axis=0)
    return np.ascontiguousarray(render_points)


register, unregister = register_classes_factory((SewingOneSide, Sewing))
