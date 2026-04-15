from typing import List

import numpy as np
from bpy.props import EnumProperty, FloatProperty, PointerProperty, IntProperty, CollectionProperty, \
    FloatVectorProperty, BoolProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from utilities.console import console
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
        return global_data.get_obj_by_uuid(self.line1_uuid)

    @property
    def line2(self):
        return global_data.get_obj_by_uuid(self.line2_uuid)


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
        if self.renderer is None:
            from ..gizmos.sewing_renderer import SewingRenderer
            self.renderer = SewingRenderer(self)

        render_points1 = calc_sewing_side_render_points(self.side1)
        render_points2 = calc_sewing_side_render_points(self.side2)

        self.side1.sewing = self
        self.side2.sewing = self
        self.renderer.update_batch_edge(render_points1, render_points2)


define_temp_prop(Sewing, "need_render_update", True)
define_temp_prop(Sewing, "renderer", None)
define_temp_prop(Sewing, "sections1", lambda: [None, None])
define_temp_prop(Sewing, "sections2", lambda: [None, None])


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


def calc_sewing_geo_point(project):
    link_sections = Section.link_sections
    link_sections.clear()
    pattern_set = set()
    for sewing in project.sewings:
        ss1, ss2 = sewing.side1, sewing.side2
        pattern_set.add(ss1.line1.pattern)
        pattern_set.add(ss1.line2.pattern)
        pattern_set.add(ss2.line1.pattern)
        pattern_set.add(ss2.line2.pattern)
    for p in pattern_set:
        p.create_sections()

    # Split and link sections by sewings.
    blur_factor = 0.05
    for sewing in project.sewings:
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
                seg = max(round(sec.absolute_length() / sec.edge.pattern.granularity), 1)
                max_seg = max(max_seg, seg)
            for sec in sections:
                sec.seg = max_seg
            console.warning(i, sections)
    for p in pattern_set:
        p.forced_update()


def calc_sewing_side_edges_index(ss):
    p = ss.line1.pattern
    e1_index = e2_index = -1
    for i, e in enumerate(p.edges):
        if e.global_uuid == ss.line1_uuid:
            e1_index = i
        if e.global_uuid == ss.line2_uuid:
            e2_index = i
        if e1_index != -1 and e2_index != -1:
            break
    if e1_index == -1 or e2_index == -1:
        raise ValueError("sewing side in different pattern!!", ss.line1_uuid, ss.line2_uuid)
    return e1_index, e2_index


def calc_sewing_side_edges(ss):
    p = ss.line1.pattern
    e1_i, e2_i = calc_sewing_side_edges_index(ss)
    e_i = e1_i
    edges: List[Edge2D] = [p.edges[e_i]]
    crazy_loop = e1_i == e2_i and (ss.pos1 > ss.pos2) ^ ss.reverse
    # console.info(crazy_loop,(ss.pos1 > ss.pos2) , ss.reverse)
    step = -1 if ss.reverse else 1
    if crazy_loop:
        e_i = (e_i + step) % len(p.edges)
        edges.append(p.edges[e1_i])
    while e_i != e2_i:
        e_i = (e_i + step) % len(p.edges)
        edges.append(p.edges[e_i])
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

    e = edges[0]

    points = e.render_points

    scans = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    length = e.length
    target = length * ss.pos1
    start_i = np.searchsorted(scans, target, side='right')
    start_i = max(start_i, 1)
    left_i, right_i = start_i - 1, start_i
    radio = (target - scans[left_i]) / (scans[right_i] - scans[left_i])
    start_point = points[left_i] * (1 - radio) + points[right_i] * radio

    e = edges[-1]
    points = e.render_points
    scans = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    length = e.length
    target = length * ss.pos2
    end_i = np.searchsorted(scans, target, side='left')
    end_i = min(end_i, len(points) - 1)
    left_i, right_i = end_i - 1, end_i
    radio = (target - scans[left_i]) / (scans[right_i] - scans[left_i])
    end_point = points[left_i] * (1 - radio) + points[right_i] * radio

    render_points.append(start_point)
    if len(edges) == 1:
        render_points.extend(e.render_points[start_i:end_i])
    else:
        render_points.extend(edges[0].render_points[start_i:])
        for i in range(1, len(edges) - 1):
            render_points.extend(edges[i].sections)
        render_points.extend(edges[-1].render_points[:end_i])
    render_points.append(end_point)
    return render_points


register, unregister = register_classes_factory((SewingOneSide, Sewing))
