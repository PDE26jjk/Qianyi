import numpy as np
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..model.sewing import SewingOneSide
from ..model.pattern import interactive_edit_allowed
from ..model.generator import refuse_generated_edit
from ..gizmos.moving_curve import TempPoint
from ..model.geometry import Edge2D, Vertex2D
from ..model.model_data import owner_pattern
from ..utilities.console import console_print, console
from ._2d_operator_base import Operator2DBase
from .. import global_data
from ..declarations import Operators
from ..gizmos.temp_draw_manager import TempDrawManager
from ..utilities.node_tree import get_active_node_tree


def sewing_index(project, sewing) -> int:
    """Where one seam sits in the project, or -1 when it is not there.

    Not `sewing.get_index()`: that reads `path_from_id()`, which needs the
    PropertyGroup to be attached to its ID. The pointer a caller has here comes
    from a temp prop on a side, so a seam that was already removed - or a side
    whose temp slot shifted when the collection moved - raises there instead of
    answering. That is what made deleting the third seam fail.
    """
    for index, candidate in enumerate(project.sewings):  # loop: one seam per entry
        if candidate == sewing or candidate.global_uuid == sewing.global_uuid:
            return index
    return -1


def _vertex_is_orphan(pattern, index) -> bool:
    """Whether no outline edge and no remaining line edge uses this vertex."""
    for edge in pattern.edges:
        if index in (int(edge.vertex_index[0]), int(edge.vertex_index[1])):
            return False
    for line in pattern.internal_lines:
        for edge in line.edges:
            if index in (int(edge.vertex_index[0]), int(edge.vertex_index[1])):
                return False
    return True


def _shift_index(edge, removed_index):
    """Close the gap a removed vertex left in every edge that named it."""
    for slot in (0, 1):
        if int(edge.vertex_index[slot]) > removed_index:
            edge.vertex_index[slot] = int(edge.vertex_index[slot]) - 1


def _chain_vertices(edges) -> list:
    """The vertex indices one chain runs through, in order.

    Edge `index` runs from position `index` to position `index + 1`, so this is
    one entry longer than the chain: an open line's last entry is the far end
    nothing starts from, and a loop's repeats its first, which is the wrap a
    walk along the chain closes over.
    """
    if len(edges) == 0:
        return []
    positions = [int(edges[0].vertex_index[0])]
    for edge in edges:  # loop: one entry per edge end
        positions.append(int(edge.vertex_index[1]))
    return positions


def _next_survivor(alive, position, is_loop) -> int:
    """The first surviving position from `position` on, or -1 when there is none.

    A loop wraps, so a walk that runs off the end of its own positions comes
    back to the first survivor; an open line that finds none has no far vertex
    left for the edge that was walking to one.
    """
    span = len(alive)
    for step in range(span if is_loop else span - position):
        candidate = (position + step) % span if is_loop else position + step
        if alive[candidate]:
            return candidate
    return -1


def _splice_chain(line, deleted) -> tuple:
    """The edges of one chain that survive, and the two ends each survivor has.

    `deleted` holds the vertex indices the selection marked, and the rule is
    the one the outline already follows: an edge whose start vertex is deleted
    goes with it, and every other edge is re-pointed to the next surviving
    vertex of the chain, so the run of deleted vertices between the two is
    bridged. A deleted vertex therefore means the vertex before it carries on
    to the vertex after it, and a deleted edge means its two ends are deleted,
    which bridges the same way. An edge whose run reaches the end of an open
    chain has no vertex left to run to and goes as well - that is what
    shortens a line whose far end is deleted. A loop wraps to its own first
    survivor, and fewer than two surviving vertices cannot hold a chain, so
    nothing survives then.
    """
    count = len(line.edges)
    if count == 0:
        return [], []
    chain = _chain_vertices(line.edges)
    # A loop's last entry repeats its first, so its positions are the start
    # vertices of its edges; an open line adds the far end it finishes on.
    span = count if line.is_loop else count + 1
    alive = [chain[position] not in deleted for position in range(span)]
    if sum(alive) < 2:
        return [], []
    kept, ends = [], []
    for index in range(count):
        if not alive[index]:
            continue
        far = _next_survivor(alive, index + 1, line.is_loop)
        if far < 0:
            continue
        kept.append(index)
        ends.append((chain[index], chain[far]))
    return kept, ends


def _control_point_marks(line, spline_points) -> dict:
    """Where these control points sit on one line: edge index -> point indices."""
    wanted = {point.global_uuid for point in spline_points}
    marks = {}
    if not wanted:
        return marks
    for index, edge in enumerate(line.edges):
        positions = [position for position, point in enumerate(edge.spline_points)
                     if point.global_uuid in wanted]
        if positions:
            marks[index] = positions
    return marks


def _touched_line_indices(pattern, vertices, spline_points) -> list:
    """The internal lines, high to low, whose chain holds these elements.

    One line at a time and from the end of the collection: a line left without
    an edge is removed, which shifts every index above it.
    """
    marked = {vertex.get_index() for vertex in vertices}
    wanted = {point.global_uuid for point in spline_points}
    touched = []
    for line_index in reversed(range(len(pattern.internal_lines))):
        line = pattern.internal_lines[line_index]
        if any(int(edge.vertex_index[slot]) in marked
               for edge in line.edges for slot in (0, 1)):
            touched.append(line_index)
        elif any(point.global_uuid in wanted
                 for edge in line.edges for point in edge.spline_points):
            touched.append(line_index)
    return touched


def _splice_line(member, line_index, deleted, marks, sewing_map, mark_impacted) -> None:
    """Take the marked elements out of one member's copy of one internal line.

    `deleted` and `marks` are indices into the pattern the selection named; every
    member of the chain holds the same chain by index, which is what lets an
    edit be written to the whole chain. A sewing that named an edge which goes
    is marked for the project to drop, a line left without edges is removed,
    and the vertices nothing references any more leave the pattern's pool - a
    vertex the outline or another line still uses stays for its own chain's
    surgery to decide about.
    """
    line = member.internal_lines[line_index]
    chain = _chain_vertices(line.edges)
    kept, ends = _splice_chain(line, deleted)
    kept_set = set(kept)
    for index in range(len(line.edges)):
        if index in kept_set:
            continue
        for sewing in sewing_map.pop(line.edges[index].global_uuid, ()):
            mark_impacted(sewing)
    # The survivors keep their own identity and take their new ends before the
    # removals below shift the edges behind them.
    for index, (start, end) in zip(kept, ends):
        edge = line.edges[index]
        edge.vertex_index[0] = int(start)
        edge.vertex_index[1] = int(end)
        for position in sorted(marks.get(index, ()), reverse=True):
            edge.spline_points.remove(position)
        if marks.get(index):
            member.refresh_collection_uuid(edge.spline_points)
    dropped = [index for index in range(len(line.edges)) if index not in kept_set]
    for index in sorted(dropped, reverse=True):
        line.edges.remove(index)
    if len(line.edges) == 0:
        member.internal_lines.remove(line_index)
    else:
        member.refresh_collection_uuid(line.edges)
    # Every vertex a survivor still runs through is referenced; the ones the
    # chain held before its surgery are what can be left behind.
    for position in sorted(set(chain), reverse=True):
        if not _vertex_is_orphan(member, position):
            continue
        member.vertices.remove(position)
        for edge in member.edges:
            _shift_index(edge, position)
        for other in member.internal_lines:
            for edge in other.edges:
                _shift_index(edge, position)
    member.refresh_collection_uuid(member.vertices)
    member.refresh_collection_uuid(member.edges)
    for other in member.internal_lines:
        member.refresh_collection_uuid(other.edges)


def delete_line_elements(pattern, line_index, vertices=(), spline_points=(), *,
                         sewing_map=None, mark_impacted=None) -> None:
    """Take these elements out of one internal line, on every copy of the pattern.

    `vertices` are points of the line and `spline_points` are control points of
    its edges, both the objects the selection picked on `pattern`. They are
    read as indices and written to every member of the instance chain, which
    holds the same chain by index.

    Deleting a point splices it out of the chain: the point before it carries
    on to the point after it. Deleting an edge means deleting its two ends,
    which bridges exactly the way the outline bridges when one of its edges
    goes. A point at the end of an open line has no point after it to carry on
    to, so the edge that ran to it goes with it - which is why deleting the
    last edge of an open line takes the edge before it as well, the point the
    two shared being deleted - and a line left without an edge is removed. The
    points no remaining edge references leave the pattern's pool; a point the
    outline or another line still uses stays in it.
    """
    line = pattern.internal_lines[line_index]
    deleted = {vertex.get_index() for vertex in vertices}
    marks = _control_point_marks(line, spline_points)
    sewing_map = {} if sewing_map is None else sewing_map
    mark_impacted = (lambda _sewing: None) if mark_impacted is None else mark_impacted
    # One Sketch serves the whole instance chain, so the splice is written once
    # and every member reads it; the members rebuild their own mesh afterwards.
    _splice_line(pattern, line_index, deleted, marks, sewing_map, mark_impacted)


class NODE_OT_elements_delete(Operator2DBase):
    bl_idname = Operators.ElementsDelete2D
    bl_label = "elements delete"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        project = get_active_node_tree(context)
        return project is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        qmyi = context.scene.qmyi
        edit_mode = qmyi.edit_mode
        project = get_active_node_tree(context)

        if edit_mode == "PATTERN":
            selected_patterns = project.get_selected_objects_by_mode("PATTERN")
            if len(selected_patterns) == 0:
                return {"CANCELLED"}
            project.remove_patterns(selected_patterns)

        elif edit_mode == "EDGE":
            draw_manager: TempDrawManager = global_data.temp_draw_manager
            draw_manager.clear()
            pattern_set = set()
            point_set = set()
            objs = project.get_selected_objects_by_mode("EDGE", "EDGE_VERTEX")
            for obj in objs:
                pattern = owner_pattern(obj)
                if pattern is not None:
                    pattern_set.add(pattern)
            # One Sketch serves a whole instance chain, so two selected elements
            # of two members are one edit: the set is keyed by Sketch.
            by_sketch = {}
            for pattern in pattern_set:
                by_sketch.setdefault(int(pattern.sketch_uuid), pattern)
            pattern_set = set(by_sketch.values())
            for candidate in pattern_set:
                if refuse_generated_edit(self, project, candidate):
                    return {"CANCELLED"}
            for p in pattern_set:
                for v in p.vertices:
                    v.impacted = False
                for e in p.edges:  # the outline's own control points
                    for sp in e.spline_points:
                        sp.impacted = False
                for line in p.internal_lines:
                    for e in line.edges:
                        for sp in e.spline_points:
                            sp.impacted = False
            for obj in objs:
                if isinstance(obj, Edge2D):
                    point_set.add(obj.vertex0)
                    point_set.add(obj.vertex1)
                elif isinstance(obj, Vertex2D):
                    point_set.add(obj)
            for p in point_set:
                p.impacted = True

            blocked = False  # a pattern whose outline would intersect is left alone
            sewing_map = dict()

            def insert_sewing_map(idx, sw):
                if idx not in sewing_map:
                    sewing_map[idx] = []
                sewing_map[idx].append(sw)

            def mark_impacted(sw):
                sw.impacted = True
                # The sewing is reachable through all four of its line uuids;
                # forget every one of them, so a later pattern of this same
                # delete cannot touch a sewing that is already gone.
                for key in (sw.side1.line1_uuid, sw.side1.line2_uuid,
                            sw.side2.line1_uuid, sw.side2.line2_uuid):
                    sewing_map.pop(key, None)

            for s in project.sewings:
                s.impacted = False
                insert_sewing_map(s.side1.line1_uuid, s)
                insert_sewing_map(s.side1.line2_uuid, s)
                insert_sewing_map(s.side2.line1_uuid, s)
                insert_sewing_map(s.side2.line2_uuid, s)

            for p in pattern_set:
                edges_del = []
                edges_rest = []  # [(e_uuid,e_v0_uuid,e_new_v1_uuid),...]
                spline_del = []  # Corresponding to edges_rest
                for e in p.edges:
                    if e.vertex0.impacted:
                        edges_del.append(e.get_index())
                    else:
                        edges_rest.append([e, e.vertex0.global_uuid])
                        sps = []
                        for i, sp in enumerate(e.spline_points):
                            if sp.impacted:
                                sps.append(i)
                        spline_del.append(sps)
                if len(edges_rest) < 2:
                    console.error('rest edges too few!')
                    break
                checking_edge_points = []
                for i, e in enumerate(edges_rest):
                    start_ind = e[0].get_index()
                    ind = (start_ind + 1) % len(p.edges)
                    while ind != start_ind and p.edges[ind].vertex0.impacted:
                        ind = (ind + 1) % len(p.edges)
                    new_vertex = p.edges[ind].vertex0
                    e.append(new_vertex.global_uuid)
                    mc = draw_manager.add_moving_curve(e[0])
                    e[0] = e[0].global_uuid
                    mc.vertex1 = TempPoint(new_vertex.co)
                    sps = spline_del[i]
                    if len(sps) > 0:
                        for j in sorted(sps, reverse=True):
                            del mc.spline_points[j]
                    mc.update()
                    checking_edge_points.append(mc.render_points[:-1])
                    # console.info(e, mc.render_points[:-1])
                checking_edge_points = np.concatenate(checking_edge_points, dtype=np.float32)
                if not interactive_edit_allowed(context, checking_edge_points):
                    blocked = True
                    break
                # Nothing has been written up to here, so a pattern whose
                # outline would cross itself is left exactly as it was - its
                # internal lines included.
                #
                # An internal line the selection touched is spliced first. One
                # Sketch serves the whole instance chain, so the write happens
                # once and every member reads it: the chain bridges the deleted
                # points the way the outline does, a line left without an edge
                # is removed, and the vertices nothing references any more leave
                # the pool. A vertex the outline shares stays - the outline's own
                # surgery below removes it.
                marked_vertices = [v for v in p.vertices if v.impacted]
                marked_points = [point for line in p.internal_lines
                                 for edge in line.edges
                                 for point in edge.spline_points if point.impacted]
                for line_index in _touched_line_indices(p, marked_vertices, marked_points):
                    delete_line_elements(p, line_index, marked_vertices, marked_points,
                                         sewing_map=sewing_map,
                                         mark_impacted=mark_impacted)
                for i in sorted(edges_del, reverse=True):
                    edge_uuid = p.edges[i].global_uuid
                    if edge_uuid in sewing_map:
                        for s in sewing_map[edge_uuid]:
                            mark_impacted(s)
                        sewing_map.pop(edge_uuid, None)
                    p.edges.remove(i)
                p.refresh_collection_uuid(p.edges)
                vertices_del = [v.get_index() for v in p.vertices if v.impacted]
                for i in sorted(vertices_del, reverse=True):
                    p.vertices.remove(i)
                    for line in p.internal_lines:
                        for edge in line.edges:
                            _shift_index(edge, i)
                p.refresh_collection_uuid(p.vertices)
                for line in p.internal_lines:
                    p.refresh_collection_uuid(line.edges)
                for i, e_ in enumerate(edges_rest):
                    e_index = global_data.get_obj_by_uuid(e_[0]).get_index()
                    v0_index = global_data.get_obj_by_uuid(e_[1]).get_index()
                    v1_index = global_data.get_obj_by_uuid(e_[2]).get_index()
                    e = p.edges[e_index]
                    e.vertex_index[0] = v0_index
                    e.vertex_index[1] = v1_index
                    sps = spline_del[i]
                    if len(sps) > 0:
                        for j in sorted(sps, reverse=True):
                            e.spline_points.remove(j)
                        e.refresh_collection_uuid(e.spline_points)
                # The sewings that lost a line have to go before the patterns are
                # marked: marking walks every sewing in the project and a
                # deleted edge no longer resolves.
                project.remove_impacted_sewings()
                # Every write above went straight into the Sketch's own
                # collections - edges and vertices removed, indices shifted,
                # spline points dropped - so the write signal is sent here: the
                # patterns that read the Sketch are marked and their display is
                # rebuilt.
                sketch = p.sketch
                if sketch is not None:
                    sketch.geometry_written()
                    # One Sketch serves the whole instance chain, so the
                    # removals are one edit for every member: the Sketch builds
                    # each of their meshes.
                    sketch.rebuild_meshes()
            if blocked:
                context.area.tag_redraw()
            draw_manager.clear()
            project.remove_impacted_sewings()
            project.clear_edge_finder()
        elif edit_mode == "SEWING":
            objs = project.get_selected_objects_by_mode("SEWING")
            # A set: a seam has two sides, so selecting both of them names the
            # same seam twice, and removing an index twice would remove another
            # seam after the collection shifted.
            del_idx_list = set()
            for obj in objs:
                if not isinstance(obj, SewingOneSide):
                    continue
                sewing = obj.sewing
                if sewing is None:
                    console.warning("a selected seam is no longer in the "
                                    "project, skipping it")
                    continue
                index = sewing_index(project, sewing)
                if index == -1:
                    console.warning("a selected seam is gone, skipping it")
                    continue
                del_idx_list.add(index)
            patterns = project.patterns_of(project.sewings[i] for i in sorted(del_idx_list))
            for i in sorted(del_idx_list, reverse=True):
                for attribute in ("pattern1", "pattern2"):  # loop: the two patterns
                    target = getattr(project.sewings[i], attribute, None)
                    if target is not None:
                        target.need_sewing_update = True
                project.sewings.remove(i)
            project.refresh_collection_uuid(project.sewings)
            # The seams that are left have to be linked again: the ones that went
            # were the only reason their pieces were cut where they are, and a
            # pattern held out of the mesh by one of them has to come back.
            project.sewings_changed(patterns)
        project.clear_selected_objects_by_mode(edit_mode)
        context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory((NODE_OT_elements_delete,))
