"""Merge the selected points into one point per run of connected points."""

import numpy as np
from bpy.types import Context
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model import pattern_geometry as geometry
from ..model.generator import refuse_generated_edit
from ..model.geometry import Edge2D, Vertex2D
from ..model.model_data import owner_pattern
from ..model.pattern import interactive_edit_allowed
from ..utilities.node_tree import get_active_node_tree
from ._2d_elements_delete import _chain_vertices, _shift_index
from ._2d_operator_base import Operator2DBase, select_vertices


def chains_of(pattern) -> list:
    """Every chain of one panel as ``(edges, is_loop)``, the outline first."""
    return [(pattern.edges, True)] + [(line.edges, bool(line.is_loop))
                                      for line in pattern.internal_lines]


def runs_of(pattern, edges, is_loop) -> list:
    """The maximal runs of selected points of one chain, as ``(start, length)``.

    A position of a chain is one of its points: position `p` is the point edge `p`
    starts on, and an open chain has one more position at its far end. A run is a
    set of consecutive selected positions - a selected edge picks both of its ends
    - and a loop is walked from a position outside every run, so a run that
    crosses the loop's own end comes back as one run.
    """
    count = len(edges)
    if count == 0:
        return []
    chain = _chain_vertices(edges)
    span = count if is_loop else count + 1
    flagged = [bool(edges[count - 1].vertex1.impacted) if position >= count
               else bool(edges[position].vertex0.impacted)
               for position in range(span)]
    if is_loop and all(flagged):
        return [(0, span)]
    first = 0
    if is_loop:  # start the walk outside every run, so a wrapping run is one run
        while flagged[first]:
            first += 1
    runs, step = [], 0
    while step < span:
        position = (first + step) % span if is_loop else step
        if not flagged[position]:
            step += 1
            continue
        length = 0
        while length < span:
            index = (position + length) % span if is_loop else position + length
            if index >= span or not flagged[index]:
                break
            length += 1
        runs.append((position, length))
        step += length
    return runs


def merge_runs(pattern) -> dict:
    """Plan the merge of every run of selected points of one panel.

    A run becomes one point at the centre of its points: the first of them keeps
    the identity and takes that place, the rest go with the edges between them,
    and the two edges that remain at the ends are re-pointed at it. Each of them
    keeps its own handle at the end that moved - it moves with that end, which is
    what leaves the half that remains the shape it had - and the handles at their
    far ends do not move at all. Selected control points of a spline edge merge
    the same way, into one control point of that edge. Nothing is written here.
    """
    merges, splines, edge_removals, vertex_removals = [], [], [], []
    for chain_index, (edges, is_loop) in enumerate(chains_of(pattern)):
        chain = _chain_vertices(edges)
        count = len(edges)
        span = count if is_loop else count + 1
        # `_chain_vertices` walks vertex indices, so the walk is over the panel's
        # own points; a run is planned before anything is written, so they hold.
        point_at = lambda position: pattern.vertices[chain[position % span]]  # noqa: E731
        for edge in edges:  # loop: one spline merge per run of control points
            splines.extend(_plan_control_points(edge))
        for start, length in runs_of(pattern, edges, is_loop):
            if length < 2:
                continue  # one point on its own is not a run to merge
            if length == span and is_loop:
                raise geometry.GeometryRefused(
                    "the whole chain is selected",
                    "a chain cannot become one point: leave one of its edges out")
            last = start + length - 1
            # A run that reaches the far end of an open chain has no edge leaving
            # it; a loop's positions wrap, so the edge that leaves is always there.
            leaving = None if last >= count and not is_loop else edges[last % count]
            run_points = [point_at(position) for position in range(start, last + 1)]
            centre = (float(np.mean([point.co[0] for point in run_points])),
                      float(np.mean([point.co[1] for point in run_points])))
            keep, gone = point_at(start), point_at(last)
            arriving = None if start == 0 and not is_loop else edges[(start - 1) % count]
            merges.append({
                "keep_uuid": int(keep.global_uuid),
                "centre": centre,
                "arriving_uuid": None if arriving is None else int(arriving.global_uuid),
                "arriving_delta": (centre[0] - float(keep.co[0]),
                                   centre[1] - float(keep.co[1])),
                # The edge that leaves the run is held by identity: the removals
                # below shift the indexes its collection is read by.
                "leaving_uuid": None if leaving is None else int(leaving.global_uuid),
                "leaving_delta": (centre[0] - float(gone.co[0]),
                                  centre[1] - float(gone.co[1])),
                "removed_edges": [(chain_index, position % count)
                                  for position in range(start, last)],
                "removed_vertices": [(int(point_at(position).global_uuid),
                                      int(point_at(position).get_index()))
                                     for position in range(start + 1, last + 1)],
            })
            edge_removals.extend(merges[-1]["removed_edges"])
            vertex_removals.extend(merges[-1]["removed_vertices"])
    if not merges and not splines:
        raise geometry.GeometryRefused(
            "no run of points is selected",
            "select two or more points next to each other on a chain, or two "
            "control points of one spline edge")
    return {"merges": merges, "splines": splines, "edge_removals": edge_removals,
            "vertex_removals": vertex_removals}


def _plan_control_points(edge) -> list:
    """The merges of the selected control points of one edge, as plans.

    A spline edge carries its own control points, and a selected run of them
    becomes one control point at the centre of the run, like a run of points
    becomes one point. Nothing else about the edge changes.
    """
    points = list(edge.spline_points)
    if len(points) < 2:
        return []
    flagged = [bool(point.impacted) for point in points]
    merges, position = [], 0
    while position < len(flagged):
        if not flagged[position]:
            position += 1
            continue
        length = 0
        while position + length < len(flagged) and flagged[position + length]:
            length += 1
        if length >= 2:
            run = points[position:position + length]
            merges.append({
                "edge_uuid": int(edge.global_uuid),
                "keep_uuid": int(run[0].global_uuid),
                "centre": (float(np.mean([point.co[0] for point in run])),
                           float(np.mean([point.co[1] for point in run]))),
                "removed": [(int(point.global_uuid), position + step)
                            for step, point in enumerate(run[1:], start=1)],
            })
        position += length
    return merges


def candidate_outline(pattern, report) -> np.ndarray:
    """The outline this merge would leave, as one sampled polyline.

    Close enough to test it for a crossing: the edges inside a run are gone, the
    edge that leaves the run moves with its end, and the edge that arrives at it
    ends on the merged point.
    """
    dropped = {(chain_index, index) for chain_index, index in report["edge_removals"]}
    moved = {merge["leaving_uuid"]: merge["leaving_delta"] for merge in report["merges"]
             if merge["leaving_uuid"] is not None}
    arrived = {merge["arriving_uuid"]: merge["arriving_delta"] for merge in report["merges"]
               if merge["arriving_uuid"] is not None}
    chunks = []
    for index, edge in enumerate(pattern.edges):  # loop: one edge of the outline
        if (0, index) in dropped or edge.render_points is None:
            continue
        points = np.asarray(edge.render_points, dtype=np.float64)
        delta = moved.get(int(edge.global_uuid))
        if delta is not None:
            points = points + np.asarray(delta, dtype=np.float64)
        end = arrived.get(int(edge.global_uuid))
        if end is not None:
            points = points.copy()
            points[-1] = points[-1] + np.asarray(end, dtype=np.float64)
        chunks.append(points[:-1])
    return np.concatenate(chunks, dtype=np.float64) if chunks else np.zeros((0, 2))


def apply_merges(pattern, report) -> None:
    """Write one panel's merges into its Sketch, and return what went."""
    chains = chains_of(pattern)
    # Every surviving edge keeps the shape it had at the end that stays: its own
    # control points at the end that moved come along with it.
    for merge in report["merges"]:
        keep = global_data.get_obj_by_uuid(merge["keep_uuid"], check_uuid=False)
        if keep is not None:
            keep.co = merge["centre"]
        for role, delta in (("arriving", merge["arriving_delta"]),
                            ("leaving", merge["leaving_delta"])):
            uuid_value = merge[f"{role}_uuid"]
            if uuid_value is None:
                continue
            edge = global_data.get_obj_by_uuid(uuid_value, check_uuid=False)
            if edge is None:
                continue
            for point in _moved_control_points(edge, arrives=role == "arriving"):
                point.co = (point.co[0] + delta[0], point.co[1] + delta[1])
    for merge in report["splines"]:  # loop: one control point run per edge
        edge = global_data.get_obj_by_uuid(merge["edge_uuid"], check_uuid=False)
        keep = global_data.get_obj_by_uuid(merge["keep_uuid"], check_uuid=False)
        if edge is None or keep is None:
            continue
        keep.co = merge["centre"]
        for _uuid, index in sorted(merge["removed"], key=lambda item: item[1],
                                   reverse=True):
            edge.spline_points.remove(index)
    for chain_index, edges in enumerate(chains):  # loop: one collection per chain
        indexes = sorted({index for position, index in report["edge_removals"]
                          if position == chain_index}, reverse=True)
        for index in indexes:  # loop: RNA removes per item, highest first
            edges[0].remove(index)
    for uuid_value, index in sorted(report["vertex_removals"],
                                    key=lambda item: item[1], reverse=True):
        pattern.vertices.remove(index)
        for edge in pattern.sketch.all_edges():
            _shift_index(edge, index)
    # A removal retires the wrappers the collections handed out, and the map has
    # to name the ones they hold now: the edges below are read back by identity.
    refresh_ids(pattern)
    for merge in report["merges"]:  # loop: one re-pointed edge per run
        if merge["leaving_uuid"] is None:
            continue
        edge = global_data.get_obj_by_uuid(merge["leaving_uuid"], check_uuid=False)
        keep = global_data.get_obj_by_uuid(merge["keep_uuid"], check_uuid=False)
        if keep is not None:
            if edge is not None:
                edge.vertex_index[0] = keep.get_index()
    for merge in report["merges"]:  # loop: one re-pointed edge per run
        if merge["arriving_uuid"] is None:
            continue
        edge = global_data.get_obj_by_uuid(merge["arriving_uuid"], check_uuid=False)
        keep = global_data.get_obj_by_uuid(merge["keep_uuid"], check_uuid=False)
        if edge is not None and keep is not None:
            edge.vertex_index[1] = keep.get_index()


def _moved_control_points(edge, arrives) -> list:
    """The control points of one edge that belong to the end that moved.

    A Bezier has one handle at each end, and a spline is carried through control
    points: either way it is the one nearest the end that moved that comes along,
    which is what leaves the far half exactly as it was. A straight edge has
    neither, and the line follows its end on its own.
    """
    if edge.kind == "spline":
        return [edge.spline_points[-1 if arrives else 0]] if len(edge.spline_points) else []
    if edge.kind == "bezier":
        return [edge.handle2 if arrives else edge.handle1]
    return []


def refresh_ids(pattern) -> None:
    """Name the wrappers the collections hold now, after a structural write."""
    pattern.refresh_collection_uuid(pattern.vertices)
    pattern.refresh_collection_uuid(pattern.edges)
    for line in pattern.internal_lines:  # loop: one collection per line
        pattern.refresh_collection_uuid(line.edges)


def drop_sewings_on(project, chains, report) -> int:
    """Drop every seam that sat on an edge this merge removes, and count them."""
    wanted = {int(chains[chain_index][0][index].global_uuid)
              for chain_index, index in report["edge_removals"]}
    dropped = 0
    for sewing in project.sewings:  # loop: one seam per pass
        sides = (sewing.side1, sewing.side2)
        if any(int(side.line1_uuid) in wanted or int(side.line2_uuid) in wanted
               for side in sides):
            sewing.impacted = True
            dropped += 1
    if dropped:
        project.remove_impacted_sewings()
    return dropped


def _flag_selection(panel, objs) -> None:
    """Mark what the selection names on this panel: a point, or an edge and its ends."""
    for vertex in panel.vertices:
        vertex.impacted = False
    for edges, _loop in chains_of(panel):
        for edge in edges:
            edge.impacted = False
            for point in edge.spline_points:  # a control point is selectable too
                point.impacted = False
    for obj in objs:  # loop: one selected edge or point
        if owner_pattern(obj) is not panel:
            continue
        if isinstance(obj, Edge2D):  # an edge counts as both of its points
            obj.impacted = True
            obj.vertex0.impacted = True
            obj.vertex1.impacted = True
        elif isinstance(obj, Vertex2D):
            obj.impacted = True


class NODE_OT_merge_connected(Operator2DBase):
    """Merge the selected points into one point per run of connected points"""

    bl_idname = Operators.MergeConnected2D
    bl_label = "merge connected"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        if project is None or context.scene.qmyi.edit_mode != "EDGE":
            return {'CANCELLED'}
        objs = project.get_selected_objects_by_mode("EDGE", "EDGE_VERTEX")
        by_sketch = {}
        for obj in objs:  # loop: one panel per selected element
            panel = owner_pattern(obj)
            if panel is not None:
                by_sketch.setdefault(int(panel.sketch_uuid), panel)
        panels = list(by_sketch.values())
        for panel in panels:
            if refuse_generated_edit(self, project, panel):
                return {'CANCELLED'}
        prepared = []
        for panel in panels:
            _flag_selection(panel, objs)
            try:
                report = merge_runs(panel)
            except geometry.GeometryRefused as refused:
                self.refuse(refused)
                return {'CANCELLED'}
            if not interactive_edit_allowed(context, candidate_outline(panel, report)):
                return {'CANCELLED'}
            report["panel"] = panel
            prepared.append(report)
        merged, keeps, gone = 0, [], []
        for report in prepared:
            panel = report["panel"]
            chains = chains_of(panel)
            # What leaves the panel, named before it goes: the edges inside the
            # runs, the points that were merged away, and the control points of
            # the spline edges that were merged into one.
            gone.extend(int(chains[chain_index][0][index].global_uuid)
                        for chain_index, index in report["edge_removals"])
            gone.extend(uuid_value for _index, uuid_value in report["vertex_removals"])
            gone.extend(uuid_value for merge in report["splines"]
                        for uuid_value, _index in merge["removed"])
            drop_sewings_on(project, chains, report)
            apply_merges(panel, report)
            panel.refresh_collection_uuid(panel.vertices)
            panel.refresh_collection_uuid(panel.edges)
            for line in panel.internal_lines:
                panel.refresh_collection_uuid(line.edges)
            # The Sketch is what every member of the chain reads, so the write is
            # sent from it - and so is the mesh step: all of them are meshed.
            sketch = panel.require_sketch()
            sketch.geometry_written()
            sketch.rebuild_meshes()
            keeps.extend(global_data.get_obj_by_uuid(merge["keep_uuid"], check_uuid=False)
                         for merge in report["merges"])
            keeps.extend(global_data.get_obj_by_uuid(merge["keep_uuid"], check_uuid=False)
                         for merge in report["splines"])
            merged += len(report["merges"]) + len(report["splines"])
        if not merged:
            return {'CANCELLED'}
        project.forget_selected(gone)
        select_vertices(project, [vertex for vertex in keeps if vertex is not None])
        project.clear_edge_finder()
        self.report({'INFO'}, f"merged {merged} run(s) of points")
        return {'FINISHED'}

    def refuse(self, refused) -> None:
        """Report a refusal and its hints, the way every command here does."""
        self.report({'ERROR'}, refused.reason)
        for hint in refused.hints:  # loop: one report line per hint
            self.report({'INFO'}, hint)


register, unregister = register_classes_factory((NODE_OT_merge_connected,))
