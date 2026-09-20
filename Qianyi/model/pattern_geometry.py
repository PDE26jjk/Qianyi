"""Pattern geometry commands shared by the operators and the script surface.

Every command measures along the sampled curve and writes its result back as
points - a straight piece stays a straight two-point edge, a piece that has an
exact form keeps it, and every other piece becomes a cubic spline fitted within
`FIT_TOLERANCE_MM` (see `utilities/curve_fit.py`). A command is applied to every
member of the panel's instance chain, so a linked panel stays in step, and
nothing here touches Blender's selection: the operator and the script surface
are thin wrappers around these functions.

The constants below are drafting tolerances, deliberately independent of a
panel's granularity: the mesh sampling is a ceiling, not a tolerance, so the
same edit behaves the same way on a finely drafted and on a coarsely drafted
panel.
"""

from __future__ import annotations

import numpy as np

from .. import global_data
from ..utilities.curve_fit import (cumulative_length, fit_control_points,
                                   polyline_length, slice_by_arc_length)
from .generator import instance_chain
from .geometry import Edge2D
from .model_data import refresh_all_uuids

# How far a written piece may sit from the shape the command was asked for.
FIT_TOLERANCE_MM = 0.05
# How many interpolation points one fitted piece may use before the closest fit
# is kept as it stands.
FIT_MAX_CONTROL_POINTS = 12
# Two points closer than this are the same point as far as a command is
# concerned: the triangulator does not define a result for edges below this
# scale, so a command drops a produced point that lands this close to one that
# already exists, or to another point it just produced, and reports it.
MERGE_THRESHOLD_MM = 0.5


class GeometryRefused(ValueError):
    """A command refused to run: what it could not do, and what to do instead."""

    def __init__(self, reason, *hints):
        super().__init__(reason)
        self.reason = reason
        self.hints = tuple(hints)


def divide_edges(pattern, edge_indices, *, parts=None, distance=None, cuts=1) -> dict:
    """Divide each selected edge on its own.

    Every selected edge is divided with the same parameters, but independently:
    equal parts are measured along that edge, and a target length is measured
    from that edge's own start, so its last piece absorbs its own remainder.
    A selection is not treated as one long edge - turning a run of edges into a
    single curve is a different command (joining), not a division.

    Which cuts survive is decided by `MERGE_THRESHOLD_MM`: a cut that would
    leave a piece shorter than the threshold, that lands on a point which
    already exists, or that lands too close to another point, is dropped and
    counted in the report rather than written.
    """
    plan = plan_divide(pattern, edge_indices, parts=parts, distance=distance, cuts=cuts)
    pattern = plan["pattern"]
    members = _chain_members(pattern)
    report = None
    for member in members:  # loop: the same cuts in every copy of the chain
        member_report = _divide_member(member, plan)
        if report is None:
            report = member_report
    report.update({
        "action": "divide_edges",
        "mode": plan["mode"],
        "panel": pattern.name,
        "requested_cuts": plan["requested_cuts"],
        "capped": plan["capped"],
        "copies": len(members) - 1,
    })
    report["remainder"] = report["lengths"][-1] if report["lengths"] else 0.0
    return report


def plan_divide(pattern, edge_indices, *, parts=None, distance=None, cuts=1) -> dict:
    """Where the division of each selected edge would cut, without writing.

    The same measurement `divide_edges` applies, so a preview and the command
    cannot disagree. One entry per selected edge carries its own cut points (in
    the panel's own space, millimetres) and the lengths it would be divided
    into.
    """
    if (parts is None) == (distance is None):
        raise GeometryRefused("give either a part count or a distance",
                              "one of them decides where the cuts go")
    mode = "count" if parts is not None else "length"
    if parts is not None:
        requested_parts = int(parts)
        if requested_parts < 2:
            raise GeometryRefused(f"dividing into {requested_parts} part would not cut anything",
                                  "ask for two or more parts")
        distance_value = 0.0
        requested_per_edge = 0
    else:
        distance_value = float(distance)
        if distance_value <= 0.0:
            raise GeometryRefused(f"a distance of {distance_value:g} mm does not cut anything",
                                  "give a distance greater than zero")
        requested_per_edge = int(cuts)
        if requested_per_edge < 1:
            raise GeometryRefused(f"{requested_per_edge} cuts would not cut anything",
                                  "ask for one cut or more")

    order = _edge_index_list(pattern, edge_indices)
    _ensure_shape(pattern, order)
    existing = _vertex_points(pattern)
    plans = []
    for index in order:  # loop: one selected edge at a time
        table = _edge_table(pattern, index)
        if table["length"] <= 0.0:
            raise GeometryRefused(f"edge {index} of {pattern.name!r} has no length")
        if mode == "count":
            positions = [table["length"] * step / requested_parts
                         for step in range(1, requested_parts)]
            wanted = requested_parts - 1
        else:
            room = max(int((table["length"] - MERGE_THRESHOLD_MM) // distance_value), 0)
            wanted = min(requested_per_edge, room)
            positions = [distance_value * step for step in range(1, wanted + 1)]
        cuts, merged = _keep_positions(table, positions, existing)
        plans.append({
            "index": index,
            "table": table,
            "cuts": cuts,
            "merged": merged,
            "wanted_cuts": wanted,
            "lengths": _piece_lengths(table, [local for local, _ in cuts]),
        })

    if mode == "length" and not any(plan["cuts"] for plan in plans):
        longest = max(plan["table"]["length"] for plan in plans) - MERGE_THRESHOLD_MM
        raise GeometryRefused(
            f"a distance of {distance_value:g} mm does not cut any of the "
            f"{len(plans)} selected edges",
            (f"the largest distance that cuts one of them is {longest:.3f} mm",
             "a cut needs a piece of at least "
             f"{MERGE_THRESHOLD_MM:g} mm on each side of it"))
    return {
        "pattern": pattern,
        "order": order,
        "plans": plans,
        "mode": mode,
        "points": [point for plan in plans for _, point in plan["cuts"]],
        "requested_cuts": ((requested_parts - 1) if mode == "count" else requested_per_edge)
                          * len(order),
        "capped": any(len(plan["cuts"]) != plan["wanted_cuts"] for plan in plans),
    }


def selected_edge_run(project):
    """The edges the pattern editor has selected, as (panel, indices).

    This is what a selection-driven command acts on: the operator and the script
    surface both come through here, so "the command uses the selection" is one
    rule rather than one per command. A selection is stored as uuids and the map
    from a uuid to an object is not something Blender's undo restores, so a
    selection that cannot be resolved is retried once after rebuilding the map -
    which is what a re-run of the command from the redo panel needs.
    """
    uuids = [entry.uuid for entry in project.selected_edges]  # loop: one uuid per entry
    if not uuids:
        raise GeometryRefused("no edge is selected",
                              "select the edges to divide")
    edges = _edges_of_uuids(uuids)
    if len(edges) < len(uuids):
        refresh_all_uuids()
        edges = _edges_of_uuids(uuids)
    if not edges:
        raise GeometryRefused("no edge is selected",
                              "select the edges to divide")
    pattern = edges[0].pattern
    for edge in edges:  # loop: one panel and home check per selected edge
        if edge.pattern != pattern:
            raise GeometryRefused("the selected edges are on more than one panel",
                                  "divide the edges of one panel at a time")
        if ".internal_lines[" in edge.path_from_id():
            raise GeometryRefused("that edge belongs to an internal line",
                                  "dividing an internal line is not offered yet")
    return pattern, sorted({edge.get_index() for edge in edges})


def _edges_of_uuids(uuids) -> list:
    """The edges among these uuids, skipping the ones that do not resolve."""
    edges = []
    for uuid_value in uuids:  # loop: one identity lookup per selected edge
        try:
            edge = global_data.get_obj_by_uuid(uuid_value, check_uuid=True)
        except Exception:
            edge = None
        if isinstance(edge, Edge2D):
            edges.append(edge)
    return edges


def _edge_index_list(pattern, edge_indices) -> list:
    """The edge indices to divide: any selection of the panel's outline edges."""
    count = len(pattern.edges)
    if count < 1:
        raise GeometryRefused(f"{pattern.name!r} has no edges to divide")
    indices = sorted({int(index) for index in edge_indices})
    if not indices:
        raise GeometryRefused("no edge is selected",
                              "select the edges to divide")
    for index in indices:  # loop: one bounds check per selected index
        if not 0 <= index < count:
            raise GeometryRefused(f"{pattern.name!r} has no edge {index}",
                                  f"it has {count} edges")
    return indices




def _chain_members(pattern) -> list:
    """The panel and its copies, refusing a chain whose copies have drifted."""
    members = instance_chain(pattern)
    for member in members:  # loop: one shape comparison per copy
        if (len(member.vertices) != len(pattern.vertices)
                or len(member.edges) != len(pattern.edges)):
            raise GeometryRefused(
                f"{member.name!r} is a copy of {pattern.name!r} with a different shape",
                ("copies are edited together; detach or rebuild before editing one",))
    return members


def _vertex_points(pattern) -> np.ndarray:
    """The panel's vertex positions, for the merge threshold's distance check."""
    return np.array([[float(vertex.co[0]), float(vertex.co[1])]
                     for vertex in pattern.vertices], dtype=np.float64)


def _edge_table(pattern, index) -> dict:
    """The sampled polyline and the length of one edge."""
    edge = pattern.edges[index]
    points = np.asarray(edge.render_points, dtype=np.float64)
    if points.ndim != 2 or len(points) < 2:
        raise GeometryRefused(f"edge {index} of {pattern.name!r} has no shape to divide")
    return {"points": points, "length": polyline_length(points)}


def _ensure_shape(pattern, order):
    """Refresh a panel whose sampled edges are missing, so a cut can measure."""
    for index in order:  # loop: one state check per selected edge
        if pattern.edges[index].render_points is None:
            pattern.forced_update()
            return


def _keep_positions(table, positions, existing) -> tuple[list, int]:
    """The cuts that can be written on one edge, and how many were dropped.

    A cut is dropped when it would leave a piece shorter than the merge
    threshold, and when the point it produces is closer than the threshold to a
    point that already exists or to another cut. The check is made against the
    points, not only along the curve, because a narrow panel can bring two
    positions that are far apart along the outline close together in space.
    """
    length = table["length"]
    cuts = []
    dropped = 0
    for position in positions:  # loop: one cut at a time
        local = float(position)
        if local < MERGE_THRESHOLD_MM or length - local < MERGE_THRESHOLD_MM:
            dropped += 1
            continue
        point = _point_on(table["points"], local)
        if _too_close(point, existing, cuts):
            dropped += 1
            continue
        cuts.append((local, point))
    return cuts, dropped


def _point_on(points, local_length):
    """The point at one arc length along a sampled edge."""
    lengths = cumulative_length(points)
    local_length = min(max(float(local_length), 0.0), float(lengths[-1]))
    return np.array((np.interp(local_length, lengths, points[:, 0]),
                     np.interp(local_length, lengths, points[:, 1])), dtype=np.float64)


def _too_close(point, existing, cuts) -> bool:
    """Whether a produced point is within the merge threshold of another."""
    if len(existing) and float(np.sqrt(((existing - point) ** 2).sum(axis=1)).min()) < MERGE_THRESHOLD_MM:
        return True
    # loop: the cuts this command has produced so far on this edge
    for _, other in cuts:
        if float(np.hypot(*(other - point))) < MERGE_THRESHOLD_MM:
            return True
    return False


def _divide_member(pattern, plan) -> dict:
    """Write one member's cuts, and return what happened."""
    ends = _sewing_ends(pattern, plan["plans"])
    warnings = []
    pieces = {}
    # Descending index: cutting an edge adds the pieces after it, so the indices
    # of the edges still to be cut do not move.
    for plan_edge in sorted(plan["plans"], key=lambda entry: entry["index"], reverse=True):
        index = plan_edge["index"]
        warnings.extend(_split_edge(pattern, index,
                                    [local for local, _ in plan_edge["cuts"]],
                                    plan_edge["table"]))
        if plan_edge["cuts"]:
            pieces[index] = _piece_table(pattern, index, plan_edge)
    pattern.refresh_collection_uuid(pattern.edges)
    pattern.refresh_collection_uuid(pattern.vertices)
    # `forced_update` and the mesh rebuild are what every geometry edit does;
    # the one thing this command must not do is rebuild the sections itself,
    # where a seam's linking already owns that.
    pattern.forced_update()
    moved = _remap_sewing_ends(pattern, ends, pieces)
    relinked = _mark_sewings_for_relink(pattern, ends)
    pattern.generate_mesh()
    return {
        "parts": len(plan["order"]) + sum(len(plan_edge["cuts"]) for plan_edge in plan["plans"]),
        "cut_count": sum(len(plan_edge["cuts"]) for plan_edge in plan["plans"]),
        "merged": sum(plan_edge["merged"] for plan_edge in plan["plans"]),
        "edges": [{"index": plan_edge["index"],
                   "cuts": len(plan_edge["cuts"]),
                   "parts": len(plan_edge["lengths"]),
                   "merged": plan_edge["merged"],
                   "lengths": plan_edge["lengths"]}
                  for plan_edge in plan["plans"]],
        "lengths": [length for plan_edge in plan["plans"] for length in plan_edge["lengths"]],
        "warnings": warnings,
        "sewings_moved": moved,
        "sewings_marked": relinked,
        "piece_uuids": _piece_uuids(pattern, plan, pieces),
    }


def _mark_sewings_for_relink(pattern, ends) -> int:
    """Set the signal on both panels of every seam this command re-pointed.

    The same two lines the sewing editor writes after it edits or removes a
    seam: a seam whose ends moved has to be linked again, and only the panels
    that own its sides can say so.
    """
    project = pattern.project
    marked = set()
    for end in ends:  # loop: one seam endpoint per recorded end
        if end["sewing"] in marked:
            continue
        marked.add(end["sewing"])
        sewing = project.sewings[end["sewing"]]
        for attribute in ("pattern1", "pattern2"):  # loop: the two sides' panels
            target = getattr(sewing, attribute, None)
            if target is not None:
                target.need_sewing_update = True
    return len(marked)


def _piece_table(pattern, index, plan_edge) -> list:
    """The pieces one divided edge was written as: (uuid, start, end) in order."""
    table = []
    arc = 0.0
    for position, length in enumerate(plan_edge["lengths"]):  # loop: one piece per length
        table.append((pattern.edges[index + position].global_uuid, arc, arc + length))
        arc += length
    return table


def _piece_uuids(pattern, plan, pieces) -> list:
    """The uuids of every piece the selected edges were divided into.

    An edge of the selection that no cut landed on is a piece of its own, so it
    is in the list as it stands.
    """
    uuids = []
    for index in plan["order"]:  # loop: one selected edge per entry
        table = pieces.get(index)
        if table:
            uuids.extend(uuid_value for uuid_value, _, _ in table)
        else:
            uuids.append(pattern.edges[index].global_uuid)
    return uuids


def _split_edge(pattern, edge_index, local_cuts, table) -> list:
    """Rewrite one edge as the pieces its cuts describe.

    Returns the fit warnings. The first piece keeps the edge object, so a sewing
    that pointed at it still does; the pieces after it are new edges.
    """
    points = table["points"]
    length = table["length"]
    bounds = [0.0, *sorted(local_cuts), length]
    pieces = [slice_by_arc_length(points, bounds[step], bounds[step + 1])
              for step in range(len(bounds) - 1)]  # loop: one piece per interval
    # Re-fetch the edge: adding an edge to the collection reallocates it, so a
    # wrapper taken before the first cut cannot be written to any more.
    edge = pattern.edges[edge_index]
    start_index = int(edge.vertex_index[0])
    end_index = int(edge.vertex_index[1])
    vertex_index = start_index
    warnings = []
    for position, piece in enumerate(pieces):  # loop: one RNA edge object per piece
        last = position == len(pieces) - 1
        if last:
            next_index = end_index
        else:
            next_index = pattern.add_vertex((float(piece[-1][0]), float(piece[-1][1])))
            pattern.vertices[next_index].get_temp_data()
        if position == 0:
            target = edge
        else:
            target = pattern.edges.add()
            target.pattern = pattern
            target.get_temp_data()
        target.vertex_index[0] = vertex_index
        target.vertex_index[1] = next_index
        reached, error = _write_piece(target, piece)
        # Only these edges: the command made them, so it has to give them their
        # sampled points and their renderer. Nothing else follows from this - no
        # section rebuild, no mesh rebuild - because the seam signal is what
        # tells the update path to do that.
        target.update(pattern)
        if not reached:
            warnings.append({"edge": edge_index, "piece": position, "error_mm": error})
        if position > 0:
            pattern.edges.move(len(pattern.edges) - 1, edge_index + position)
        vertex_index = next_index
    return warnings


def _write_piece(edge, piece) -> tuple[bool, float]:
    """Write one piece of a curve as the shape it came from.

    Two control points mean the piece is straight within the tolerance, so it is
    written as a straight edge; anything else becomes a spline through the
    fitted control points, which is what every later command expects to find.
    """
    control, reached, error = fit_control_points(piece, FIT_TOLERANCE_MM,
                                                 FIT_MAX_CONTROL_POINTS)
    if len(control) < 3:
        edge.set_curve("straight")
    else:
        edge.set_curve("spline", points=[(float(point[0]), float(point[1]))
                                         for point in control[1:-1]])
    return reached, error


def _piece_lengths(table, local_cuts) -> list:
    """The arc length of every piece one edge is divided into."""
    edges = [0.0, *sorted(local_cuts), table["length"]]
    return [edges[step + 1] - edges[step] for step in range(len(edges) - 1)]


def _sewing_ends(pattern, plans) -> list:
    """Every sewing endpoint that sits on one of the selected edges.

    Taken before anything is written: an endpoint is remembered as the edge it
    was on and how far along that edge it is, which is what survives a division
    of that edge.
    """
    run = {}
    for plan_edge in plans:  # loop: one selected edge per entry
        run[pattern.edges[plan_edge["index"]].global_uuid] = plan_edge
    ends = []
    for sewing_index, sewing in enumerate(pattern.project.sewings):  # loop: one RNA sewing per project entry
        for side_index, side in enumerate(sewing.sides):  # loop: the two sides of one sewing
            for which, uuid_value, pos in ((1, side.line1_uuid, side.pos1),
                                           (2, side.line2_uuid, side.pos2)):  # loop: the two ends of one side
                plan_edge = run.get(uuid_value)
                if plan_edge is None:
                    continue
                points = plan_edge["table"]["points"]
                index = min(max(int(round(float(pos) * (len(points) - 1))), 0), len(points) - 1)
                lengths = cumulative_length(points)
                ends.append({"sewing": sewing_index, "side": side_index, "which": which,
                             "index": plan_edge["index"], "arc": float(lengths[index]),
                             "point": np.array(points[index], dtype=np.float64)})
    return ends


def _remap_sewing_ends(pattern, ends, pieces) -> int:
    """Put every sewing endpoint back on the piece that replaced its edge.

    The endpoint keeps the place it was drawn at: its position is the parameter
    of the point on the new edge closest to the point it had, so a seam looks
    the way it did before the division.
    """
    if not ends:
        return 0
    project = pattern.project
    moved = 0
    for end in ends:  # loop: one sewing endpoint per recorded end
        table = pieces.get(end["index"])
        if not table:
            continue
        chosen = None
        span = (0.0, 1.0)
        last = len(table) - 1
        # loop: the pieces of one divided edge, until the one holding the end
        for position, (uuid_value, arc_start, arc_end) in enumerate(table):
            # A position exactly on a cut belongs to the piece that starts
            # there, which is the same rule the section lookup uses.
            if (arc_start - 1e-9 <= end["arc"] < arc_end - 1e-9
                    or (position == last and end["arc"] <= arc_end + 1e-9)):
                chosen = (uuid_value, global_data.get_obj_by_uuid(uuid_value, check_uuid=False))
                span = (arc_start, arc_end)
                break
        if chosen is None or chosen[1] is None:
            continue
        points = chosen[1].render_points
        if points is None:
            continue
        points = np.asarray(points, dtype=np.float64)
        index = int(np.sqrt(((points - end["point"]) ** 2).sum(axis=1)).argmin())
        pos = index / max(len(points) - 1, 1)
        side = project.sewings[end["sewing"]].sides[end["side"]]
        if end["which"] == 1:
            side.line1_uuid = chosen[0]
            side.pos1 = pos
        else:
            side.line2_uuid = chosen[0]
            side.pos2 = pos
        moved += 1
    return moved
