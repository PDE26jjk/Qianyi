"""Divide the selected edge or run of edges, by arc length."""

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty
from bpy.types import Context, Event
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model import pattern_geometry as geometry
from ..model.generator import refuse_generated_edit
from ..model.qianyi_data import ensure_edit_mode
from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import Operator2DBase

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

    The command acts on the current selection, and its numbers are the
    operator's own properties, so Blender's adjust-last-operation panel re-runs
    it from the state that existed before it: a new part count or distance
    replaces the previous division instead of adding a second one. The first
    apply and the re-run are the same `execute`, and the undo step restores the
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
        name="Distance",
        description="Distance between two cuts, in millimetres",
        default=10.0,
        min=0.01,
        unit='LENGTH',
        subtype='DISTANCE',
    )
    cuts: IntProperty(
        name="Cuts",
        description="How many cuts to make at that distance, at most",
        default=1,
        min=1,
    )

    @classmethod
    def poll(cls, context: Context):
        # The mode is not part of the poll: `invoke` puts the editor into the
        # mode this command works in, so a caller never has to check the header.
        return get_active_node_tree(context) is not None

    def draw(self, context: Context):
        """The adjust-last-operation panel: the numbers this mode uses."""
        layout = self.layout
        layout.prop(self, "mode")
        if self.mode == "COUNT":
            layout.prop(self, "parts")
        else:
            layout.prop(self, "distance")
            layout.prop(self, "cuts")

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
            pattern, indices = geometry.selected_edge_run(project)
        except geometry.GeometryRefused as refused:
            self.report({'ERROR'}, refused.reason)
            for hint in refused.hints:  # loop: one report line per hint
                self.report({'INFO'}, hint)
            return {'CANCELLED'}
        if refuse_generated_edit(self, project, pattern):
            return {'CANCELLED'}
        print_sewings(project, "before")
        try:
            report = geometry.divide_edges(pattern, indices, **self.arguments())
        except geometry.GeometryRefused as refused:
            self.report({'ERROR'}, refused.reason)
            for hint in refused.hints:  # loop: one report line per hint
                self.report({'INFO'}, hint)
            return {'CANCELLED'}
        print_sewings(get_active_node_tree(context) or project, "after")
        select_pieces(project, report)
        self.report({'INFO'}, describe(report))
        return {'FINISHED'}

    def arguments(self) -> dict:
        """The model command's arguments for the mode this operator is in."""
        return arguments(self.mode, self.parts, self.distance, self.cuts)


def arguments(mode, parts, distance, cuts) -> dict:
    """The model command's arguments for one mode of the division.

    Kept out of the operator so it can be exercised without a Blender operator
    instance, which cannot be created from Python.
    """
    if mode == "COUNT":
        return {"parts": int(parts)}
    return {"distance": float(distance), "cuts": int(cuts)}


def describe(report) -> str:
    """One line for the info area: what the division produced."""
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
            f"{line1.pattern.name if line1 else '?'}"
            f"[{line1.get_index() if line1 else -1}]@{side.pos1:.4f} -> "
            f"{line2.pattern.name if line2 else '?'}"
            f"[{line2.get_index() if line2 else -1}]@{side.pos2:.4f} "
            f"rev={side.reverse}")
    return f"seam {index}: " + " | ".join(sides)


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
    uuids = report.get("piece_uuids") or []
    if not uuids:
        return 0
    project.selected_edges.clear()
    for uuid_value in uuids:  # loop: one selection entry per produced edge
        entry = project.selected_edges.add()
        entry.uuid = uuid_value
    return len(uuids)


def show_redo_panel(context: Context) -> None:
    """Ask for Blender's own redo panel once this operator has returned.

    Blender draws that panel only when asked (`screen.redo_last`), and the entry
    points it draws itself are the F9 keymap and the Edit menu; a command that
    runs from a context menu has neither in front of the user. The redo state
    only exists after the operator has returned, so the request is deferred to
    the next event loop turn rather than made from inside `execute`.
    """
    window = getattr(context, "window", None)
    screen = getattr(context, "screen", None)
    area = getattr(context, "area", None)
    region = getattr(context, "region", None)
    if window is None or screen is None or area is None or region is None:
        return

    def request():
        try:
            # `screen` has to be overridden as well: the redo operator's poll
            # reads the context's screen, not the window's, and a timer has no
            # screen of its own.
            with bpy.context.temp_override(window=window, screen=screen,
                                           area=area, region=region):
                bpy.ops.screen.redo_last('INVOKE_DEFAULT')
        except Exception as error:
            console.warning("could not open the redo panel:", error)
        return None  # one shot

    # A moment later, so the events that are still in flight from the menu or
    # the key press cannot close the popup the moment it opens.
    bpy.app.timers.register(request, first_interval=0.1)


register, unregister = register_classes_factory((NODE_OT_divide_edge,))
