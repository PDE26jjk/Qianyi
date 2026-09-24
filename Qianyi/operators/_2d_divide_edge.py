"""Divide the selected edge or run of edges, by arc length."""

import re

import numpy as np
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model import pattern_geometry as geometry
from ..model.generator import refuse_generated_edit
from ..model.model_data import owner_pattern, refresh_all_uuids
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import Operator2DBase, select_edges, show_redo_panel

# A part count above this is refused rather than attempted: the positions are
# built one by one, and a typed-in million would hang the editor before the
# merge threshold dropped all of them.
MAX_DIVIDE_PARTS = 4096

mode_property = EnumProperty(
    name="Mode",
    description="How the positions of the cuts are decided",
    items=[
        ("COUNT", "Equal parts",
         "Divide the run into this many pieces of equal arc length",),
        ("LENGTH", "Target length",
         "Cut every target length, for this many cuts, and let the last piece "
         "absorb the remainder",),
    ],
    default="COUNT",
)


class NODE_OT_divide_edge(Operator2DBase):
    """Divide the selected edge or run of edges, by arc length.

    The command acts on the current selection - outline edges, internal line
    edges, on one panel or across several - and its numbers are the operator's
    own properties, so Blender's adjust-last-operation panel re-runs it from
    the state that existed before it: a new part count or distance replaces
    the previous division instead of adding a second one. The first apply and
    the re-run are the same `execute`, and the undo step restores the
    selection the run was made from.
    """

    bl_idname = Operators.DivideEdge2D
    bl_label = "divide edge"
    bl_options = {'REGISTER', 'UNDO'}

    mode: mode_property
    parts: IntProperty(
        name="Parts",
        description="How many pieces of equal arc length the run is divided into",
        default=2,
        min=2,
        soft_max=64,
    )
    distance: FloatProperty(
        name="Distance (mm)",
        description="Distance between two cuts, in millimetres",
        default=10.0,
        min=0.5,
    )
    cuts: IntProperty(
        name="Cuts",
        description="How many cuts to make at that distance, at most",
        default=1,
        min=1,
    )
    reverse: BoolProperty(
        name="From the far end",
        description="Measure the target length from the edge's end vertex "
                    "instead of its start vertex",
        default=False,
    )

    def draw(self, context: Context):
        """The adjust-last-operation panel: the numbers this mode uses."""
        layout = self.layout
        layout.prop(self, "mode")
        if self.mode == "COUNT":
            layout.prop(self, "parts")
        else:
            layout.prop(self, "distance")
            layout.prop(self, "cuts")
            layout.prop(self, "reverse")

    def invoke(self, context: Context, event: Event):
        ensure_edit_mode(context, "EDGE", "EDGE_VERTEX")
        result = self.execute(context)
        if result == {'FINISHED'}:
            # Only the invoke path asks for the panel: a re-run from that panel
            # comes through `execute` alone, and asking again would stack one
            # panel on top of the other.
            show_redo_panel(context)
        return result

    def execute(self, context: Context):
        project = get_active_node_tree(context)
        if project is None:
            return {'CANCELLED'}
        try:
            groups = selected_division_groups(project)
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        # Every panel is refused or none is: the lock is checked before the
        # first write, so one generated panel among the selection leaves them
        # all as they were.
        for group in groups:
            if refuse_generated_edit(self, project, group["pattern"]):
                return {'CANCELLED'}
        # print_sewings(project, "before")
        try:
            report = divide_edges_on(groups, **self.arguments())
        except geometry.GeometryRefused as refused:
            return self.refuse(refused)
        # print_sewings(project, "after")
        # The outlines changed, so the finder the tools snap against is stale.
        project.clear_edge_finder()
        select_pieces(project, report)
        self.report({'INFO'}, describe(report))
        return {'FINISHED'}

    def refuse(self, refused) -> dict:
        """Report a refusal as one line: the reason, then the hints.

        The status bar shows the last report only, so a hint reported after
        the error would be all the user sees of the two; one line keeps both.
        """
        message = refused.reason
        if refused.hints:
            message += " - " + "; ".join(refused.hints)
        self.report({'ERROR'}, message)
        return {'CANCELLED'}

    def arguments(self) -> dict:
        """The model command's arguments for the mode this operator is in."""
        return arguments(self.mode, self.parts, self.distance, self.cuts, self.reverse)


def arguments(mode, parts, distance, cuts, reverse=False) -> dict:
    """The model command's arguments for one mode of the division.

    Kept out of the operator so it can be exercised without a Blender operator
    instance, which cannot be created from Python.
    """
    if mode == "COUNT":
        return {"parts": int(parts)}
    return {"distance": float(distance), "cuts": int(cuts), "reverse": bool(reverse)}


def describe(report) -> str:
    """One line for the info area: what the division produced."""
    if not report["cut_count"] and report["mode"] == "length":
        message = (f"nothing to divide on {report['panel']} "
                   f"at {report['distance']:g} mm")
        if report["merged"]:
            message += f", {report['merged']} cut(s) landed on points the panel already has"
        elif report["capped"]:
            message += (", the pieces it would leave are shorter than "
                        f"{geometry.MERGE_THRESHOLD_MM:g} mm")
        return message
    edges = len(report.get("edges", ())) or 1
    message = (f"divided {edges} edge(s) of {report['panel']} into "
               f"{report['parts']} pieces")
    if report["copies"]:
        message += f", with {report['copies']} linked copies"
    if report["merged"]:
        message += f", {report['merged']} cut(s) reused an existing point"
    if report["capped"]:
        message += ", the count was capped by the minimum piece length"
    if report["warnings"]:
        message += (f", {len(report['warnings'])} piece(s) could not be fitted "
                    f"to tolerance")
    return message


def describe_sewing(project, index) -> str:
    """One seam as text: both sides, their panels, positions and directions."""
    sewing = project.sewings[index]
    sides = []
    for side in sewing.sides:  # loop: the two sides of one seam
        line1, line2 = side.line1, side.line2
        sides.append(
            f"{_panel_name(line1)}"
            f"[{line1.get_index() if line1 else -1}]@{side.pos1:.4f} -> "
            f"{_panel_name(line2)}"
            f"[{line2.get_index() if line2 else -1}]@{side.pos2:.4f} "
            f"rev={side.reverse}")
    return f"seam {index}: " + " | ".join(sides)


def _panel_name(edge) -> str:
    """The panel an edge is on, as text: the owner of the Sketch it lives in."""
    if edge is None:
        return "?"
    panel = owner_pattern(edge)
    return panel.name if panel is not None else "?"


def print_sewings(project, label) -> None:
    """Print every seam and every panel's relink flag.

    A division re-points seam sides and sets the signal that says a seam has to
    be linked again; this is what both of those look like before and after.
    """
    console.info(f"[divide] --- {label}: {len(project.sewings)} seam(s), "
                 f"{len(project.patterns)} panel(s)")
    for index in range(len(project.sewings)):  # loop: one seam per line
        console.info(f"[divide]     {describe_sewing(project, index)}")
    flags = ", ".join(f"{pattern.name}={pattern.need_sewing_update}"
                      for pattern in project.patterns)  # loop: one panel per flag
    console.info(f"[divide]     need_sewing_update: {flags}")


def select_pieces(project, report) -> int:
    """Leave the edges the command produced selected.

    The result of a command is what the next one works on, and the pattern
    editor draws its selection, so the pieces a division left behind stay
    visible instead of the panel appearing to have lost its selection.
    """
    return select_edges(project, report.get("piece_uuids") or [])


# --- the command's own computation

def selected_division_groups(project) -> list:
    """The selected edges, as division groups: one per chain of copies.

    A selection may mix outline edges with internal line edges, and reach
    across panels. Edges of panels that are copies of one another form one
    group - copies are edited together, so a chain's selected edges are pooled
    into the division of the copy the selection reached first - and every
    other panel starts a group of its own.

    A selection is stored as uuids and the uuid map is not something Blender's
    undo restores, so a selection that does not resolve is retried once after
    the map is rebuilt - which is what a re-run from the redo panel needs.
    """
    uuids = [entry.uuid for entry in project.selected_edges]
    if not uuids:
        raise geometry.GeometryRefused("no edge is selected", "select the edges to divide")
    edges = geometry._edges_of_uuids(uuids)
    if len(edges) < len(uuids):
        refresh_all_uuids()
        edges = geometry._edges_of_uuids(uuids)
    if not edges:
        raise geometry.GeometryRefused("no edge is selected", "select the edges to divide")
    groups = []
    for edge in edges:
        pattern, line_index, index = edge_target(edge)
        group = _group_of(groups, pattern)
        group["edges"].setdefault(line_index, set()).add(index)
    return [{"pattern": group["pattern"],
             "edges": {line_index: sorted(indices)
                       for line_index, indices in group["edges"].items()}}
            for group in groups]


def _group_of(groups, pattern) -> dict:
    """The group this panel's edges belong to: one it joined, or its own.

    A chain is what shares a Sketch, so the group is keyed by the panels that
    read it: dividing through two members of one chain would cut one shape
    twice.
    """
    for group in groups:
        if pattern.global_uuid in group["members"]:
            return group
    group = {"pattern": pattern,
             "members": {member.global_uuid for member in pattern.sketch_members()},
             "edges": {}}
    groups.append(group)
    return group


def edge_target(obj) -> tuple:
    """Where a selected edge lives: (pattern, internal line index or None, index).

    The property path decides - `<owner>.edges[7]` is an outline edge and
    `<owner>.internal_lines[2].edges[7]` is the seventh edge of that line - so an
    edge is placed by where it is stored, not by a check the model could grow out
    of. The owner is the Sketch a panel draws through, or the panel itself when
    something still stores its geometry there; the pattern the command names is
    the one that owns that Sketch.
    """
    segments = re.findall(r"(\w+)\[(-?\d+)\]", obj.path_from_id())
    if (len(segments) < 2 or segments[0][0] not in ("patterns", "sketches")
            or segments[-1][0] != "edges"):
        raise geometry.GeometryRefused(
            "that selection is not an edge of a panel or of an internal line",
            "select the edges to divide in the pattern editor")
    line_index = None
    if len(segments) >= 3 and segments[1][0] == "internal_lines":
        line_index = int(segments[1][1])
    return owner_pattern(obj), line_index, int(segments[-1][1])


def _edge_collection(pattern, line_index):
    """The edge collection a target writes into: the outline, or one internal line."""
    if line_index is None:
        return pattern.edges
    return pattern.internal_lines[line_index].edges


def _edge_index_list(edges, edge_indices, where) -> list:
    """The edge indices to divide, out of one collection's edges."""
    count = len(edges)
    if count < 1:
        raise geometry.GeometryRefused(f"{where} has no edges to divide")
    indices = sorted({int(index) for index in edge_indices})
    if not indices:
        raise geometry.GeometryRefused("no edge is selected", "select the edges to divide")
    for index in indices:
        if not 0 <= index < count:
            raise geometry.GeometryRefused(f"{where} has no edge {index}",
                                           f"it has {count} edges")
    return indices


def _too_close(point, existing, cuts) -> bool:
    """Whether a produced point is within the merge threshold of another."""
    if len(existing) and float(np.sqrt(((existing - point) ** 2).sum(axis=1)).min()) \
            < geometry.MERGE_THRESHOLD_MM:
        return True
    for _, other in cuts:
        if float(np.hypot(*(other - point))) < geometry.MERGE_THRESHOLD_MM:
            return True
    return False


def divide_edges_on(groups, *, parts=None, distance=None, cuts=1, reverse=False) -> dict:
    """Divide whole groups of edges, by equal parts or a target length.

    `groups` is one entry per panel chain: the panel the numbers are measured
    on, and the edges to divide as `{line index or None: [edge indices]}` -
    `None` for the outline, a line's index in `internal_lines` for one of its
    internal lines. Every member of a chain is written with the same pieces -
    the outline and the internal lines alike, by index - so linked copies stay
    one shape. Every group is planned before any of them is written, so a
    refusal leaves every panel as it was.

    Equal parts are measured along each edge; a target length is measured from
    each edge's own start - or from its end, when `reverse` is set - so its
    last piece absorbs its own remainder. Edges are divided on their own -
    turning a run of edges into a single curve is the join command. A cut that
    would leave a piece shorter than the merge threshold, or that lands within
    it of a point that already exists, is dropped and counted rather than
    written; a distance that leaves no cut at all is reported, not refused -
    the redo panel re-runs the command on every slider tick.
    """
    if (parts is None) == (distance is None):
        raise geometry.GeometryRefused("give either a part count or a distance",
                                       "one of them decides where the cuts go")
    mode = "count" if parts is not None else "length"
    requested_parts, per_edge = int(parts or 0), int(cuts)
    distance_value = float(distance or 0.0)
    if mode == "count":
        if requested_parts < 2:
            raise geometry.GeometryRefused(
                f"dividing into {requested_parts} part would not cut anything",
                "ask for two or more parts")
        if requested_parts > MAX_DIVIDE_PARTS:
            raise geometry.GeometryRefused(
                f"{requested_parts} parts is more than the command allows",
                f"ask for {MAX_DIVIDE_PARTS} parts or fewer")
    else:
        if distance_value <= 0.0:
            raise geometry.GeometryRefused(
                f"a distance of {distance_value:g} mm does not cut anything",
                "give a distance greater than zero")
        if per_edge < 1:
            raise geometry.GeometryRefused(f"{per_edge} cuts would not cut anything",
                                           "ask for one cut or more")
    if not groups:
        raise geometry.GeometryRefused("no edge is selected", "select the edges to divide")

    planned, edge_total, claimed = [], 0, set()
    for group in groups:
        pattern = group["pattern"]
        members = geometry._chain_members(pattern)
        # Two groups that share a member would write one panel twice: the
        # selection pools a chain into one group, and this guards the groups
        # that are built by hand against getting that wrong.
        overlapping = claimed.intersection(member.global_uuid for member in members)
        if overlapping:
            raise geometry.GeometryRefused(
                "the selection divides a panel twice through its copies",
                "one group per chain of copies, the way the operator builds them")
        claimed.update(member.global_uuid for member in members)
        # One table of the points a cut may not land on, per panel: an internal
        # line's vertices are in the same pool as the outline's.
        existing = np.array([[float(vertex.co[0]), float(vertex.co[1])]
                             for vertex in pattern.vertices], dtype=np.float64)
        plans = []
        for line_index in sorted(group["edges"], key=lambda line: (line is not None, line or 0)):
            edges = _edge_collection(pattern, line_index)
            where = (f"{pattern.name!r}" if line_index is None
                     else f"{pattern.name!r} internal line {line_index}")
            order = _edge_index_list(edges, group["edges"][line_index], where)
            geometry._ensure_shape(pattern, order, edges)
            for index in order:
                table = geometry._table(pattern, index, edges)
                if table["length"] <= 0.0:
                    raise geometry.GeometryRefused(f"edge {index} of {where} has no length")
                if mode == "count":
                    asked = wanted = requested_parts - 1
                    positions = [table["length"] * step / requested_parts
                                 for step in range(1, requested_parts)]
                else:
                    asked = per_edge
                    fitting = max(int((table["length"] - geometry.MERGE_THRESHOLD_MM)
                                      // distance_value), 0)
                    wanted = min(asked, fitting)
                    # Reversed cuts measure from the far end, which lands them
                    # at the same distances counted back from it; the merge
                    # threshold reads absolute positions either way.
                    if reverse:
                        positions = [table["length"] - distance_value * step
                                     for step in range(1, wanted + 1)]
                    else:
                        positions = [distance_value * step
                                     for step in range(1, wanted + 1)]
                kept, dropped_short, dropped_close = [], 0, 0
                for position in positions:
                    if (position < geometry.MERGE_THRESHOLD_MM
                            or table["length"] - position < geometry.MERGE_THRESHOLD_MM):
                        dropped_short += 1
                        continue
                    point = geometry._point_on(table["points"], position)
                    if _too_close(point, existing, kept):
                        dropped_close += 1
                        continue
                    kept.append((float(position), point))
                plans.append({"line": line_index, "index": index,
                              "uuid": edges[index].global_uuid,
                              "table": table, "cuts": kept, "asked": asked,
                              "wanted": wanted, "short": dropped_short,
                              "merged": dropped_close,
                              "lengths": geometry._piece_lengths(
                                  table["length"], [cut for cut, _ in kept])})
        edge_total += sum(len(indices) for indices in group["edges"].values())
        planned.append({"pattern": pattern, "members": members, "plans": plans})

    # A distance that places no cut is not a refusal: the redo panel re-runs
    # the command on every slider tick, and dragging it across the range where
    # nothing fits must not turn into an error popup. The report says so and
    # the panels stand as they were. Equal parts are an explicit request, and
    # failing it stays a refusal.
    if mode == "count" and not any(plan["cuts"] for entry in planned
                                   for plan in entry["plans"]):
        raise geometry.GeometryRefused(
            f"no edge is long enough to be divided into {requested_parts} parts",
            f"a cut needs a piece of at least "
            f"{geometry.MERGE_THRESHOLD_MM:g} mm on each side of it")

    combined = _combine_reports([_divide_group(entry) for entry in planned],
                                mode, requested_parts, per_edge, edge_total)
    combined["reverse"] = bool(reverse)
    if mode == "length":
        combined["distance"] = distance_value
    return combined


def _divide_group(entry) -> dict:
    """Write one chain's cuts once, and return what happened.

    One Sketch serves the whole chain, so the cuts are written on the panel the
    numbers were measured on - its pieces are the ones the selection names. That
    panel meshes from the cut Sketch; the other readers of the Sketch were
    marked by the write and rebuild when they are next needed.
    """
    first = _divide_member(entry["pattern"], entry["plans"])
    first["panel"] = entry["pattern"].name
    first["copies"] = len(entry["members"]) - 1
    first["capped"] = any((plan["wanted"] < plan["asked"]) or plan["short"]
                          for plan in entry["plans"])
    return first


def _divide_member(pattern, plans) -> dict:
    """Write one member's cuts, and return what happened.

    The outline and the internal lines are both part of the shape a chain
    shares, so every plan is written to every member, by index. The seam ends
    are collected over all the plans: a seam that names a line of another
    member finds nothing to sit on here and is moved on that member's own
    pass.
    """
    ends = geometry._sewing_ends_on(pattern, [(plan["uuid"], plan["table"]["points"])
                                              for plan in plans])
    warnings, pieces = [], {}
    # The outline is `None`, so the sort names it False and puts it first.
    lines = sorted({plan["line"] for plan in plans},
                   key=lambda line: (line is not None, line or 0))

    def order(plan):
        # Descending within one collection: cutting an edge adds the pieces
        # after it, so the indices of the edges still to be cut do not move. The
        # collections leave each other's indices alone, so the order between
        # them is free.
        return (plan["line"] if plan["line"] is not None else -1, plan["index"])

    for plan in sorted(plans, key=order, reverse=True):
        edges = _edge_collection(pattern, plan["line"])
        warnings.extend(geometry._split_edge(
            pattern, plan["index"], [cut for cut, _ in plan["cuts"]], plan["table"], edges))
        if plan["cuts"]:
            pieces[plan["uuid"]] = geometry._piece_table_on(edges, plan["index"],
                                                            plan["lengths"])
    pattern.refresh_collection_uuid(pattern.edges)
    pattern.refresh_collection_uuid(pattern.vertices)
    for line in lines:
        pattern.refresh_collection_uuid(_edge_collection(pattern, line))
    pattern.mark_geometry_changed()
    # A split rebuilds sections part-way through the writes, so the edges the
    # command did not touch can end up sampled against that middle state. The
    # sections are recreated the way the model layer does after a structural
    # write, and every edge is sampled against them again.
    geometry._resample(pattern)
    moved = geometry._remap_sewing_ends_on(pattern, ends, pieces)
    relinked = geometry._mark_sewings(pattern, ends)
    # One Sketch serves the whole instance chain, so the cuts are one edit for
    # every member: the Sketch builds each of their meshes.
    pattern.require_sketch().rebuild_meshes()
    piece_uuids = []
    for plan in plans:
        table = pieces.get(plan["uuid"])
        if table:
            piece_uuids.extend(uuid_value for uuid_value, _, _ in table)
        else:
            piece_uuids.append(plan["uuid"])
    return {
        "parts": len(plans) + sum(len(plan["cuts"]) for plan in plans),
        "cut_count": sum(len(plan["cuts"]) for plan in plans),
        "merged": sum(plan["merged"] for plan in plans),
        "edges": [{"index": plan["index"], "line": plan["line"],
                   "cuts": len(plan["cuts"]), "merged": plan["merged"],
                   "parts": len(plan["lengths"]), "lengths": plan["lengths"]}
                  for plan in plans],
        "lengths": [length for plan in plans for length in plan["lengths"]],
        "warnings": warnings, "sewings_moved": moved, "sewings_marked": relinked,
        "piece_uuids": piece_uuids,
    }


def _combine_reports(reports, mode, requested_parts, per_edge, edge_total) -> dict:
    """One report out of one per chain: sums, and the names of the panels."""
    combined = {
        "action": "divide_edges", "mode": mode,
        "panel": ", ".join(report["panel"] for report in reports),
        "requested_cuts": ((requested_parts - 1 if mode == "count" else per_edge)
                           * edge_total),
        "parts": sum(report["parts"] for report in reports),
        "cut_count": sum(report["cut_count"] for report in reports),
        "merged": sum(report["merged"] for report in reports),
        "capped": any(report["capped"] for report in reports),
        "copies": sum(report["copies"] for report in reports),
        "edges": [edge for report in reports for edge in report["edges"]],
        "lengths": [length for report in reports for length in report["lengths"]],
        "warnings": [warning for report in reports for warning in report["warnings"]],
        "sewings_moved": sum(report["sewings_moved"] for report in reports),
        "sewings_marked": sum(report["sewings_marked"] for report in reports),
        "piece_uuids": [uuid_value for report in reports
                        for uuid_value in report["piece_uuids"]],
    }
    combined["remainder"] = combined["lengths"][-1] if combined["lengths"] else 0.0
    return combined


def divide_edges(pattern, edge_indices, *, parts=None, distance=None, cuts=1,
                 reverse=False) -> dict:
    """Divide one panel's outline edges; kept for the checker and the api."""
    return divide_edges_on([{"pattern": pattern,
                             "edges": {None: list(edge_indices)}}],
                           parts=parts, distance=distance, cuts=cuts,
                           reverse=reverse)


register, unregister = register_classes_factory((NODE_OT_divide_edge,))
