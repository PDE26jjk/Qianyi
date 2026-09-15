from bpy.props import FloatVectorProperty, BoolProperty, EnumProperty
from bpy.types import Context
from bpy.utils import register_classes_factory

from ..utilities.console import console
from ..utilities.coords_transform import region2view_coord
from ._2d_operator_base import Operator2DBase
from ..declarations import Operators
from .. import global_data
from ..model.geometry import Edge2D
from ..model.qianyi_project import edge_click_fraction
from ..utilities.node_tree import get_active_node_tree
from .select import _clear_selection, update_selection_cache

mode_property = EnumProperty(
    name="Mode",
    items=[
        ("SELECT_EDGE", "SELECT_EDGE", ""),
        ("CANCEL", "Toggle", "",),
    ],
)


class NODE_OT_add_sewing_1to1(Operator2DBase):
    bl_idname = Operators.SewingAdd1to12D
    bl_label = "add sewing one vs one edge"
    bl_options = {'BLOCKING', 'REGISTER', 'UNDO'}

    origin_mouse_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initialized: BoolProperty(default=False, options={"SKIP_SAVE"})
    mode: mode_property

    @classmethod
    def poll(cls, context: Context):
        if not context.scene.qmyi.edit_mode == "SEWING":
            return False
        project = get_active_node_tree(context)
        if project is None:
            return False
        # hover_object = context.scene.qmyi.hover_object
        # if hover_object is not None and hover_object.global_uuid != -1 and isinstance(hover_object, Edge2D):
        #     # console.info("poll true")
        #     return True
        return True

    def invoke(self, context, event):
        project = get_active_node_tree(context)
        console.info("in setup_state_machine", self.mode)
        if self.mode == "SELECT_EDGE":
            hover_object = context.scene.qmyi.hover_object
            if hover_object is not None and hover_object.global_uuid != -1 and isinstance(hover_object, Edge2D):
                if project.selected_sewing_edge1 is None:
                    project.selected_sewing_edge1 = hover_object
                    project.selected_sewing_point1 = self.click_pattern_point(context, hover_object)
                else:
                    # The direction comes from where the two edges were clicked:
                    # each half starts at the end its click is nearer, so the
                    # stitching order is the one the user pointed at.
                    sw = project.add_sewing1to1_from_points(
                        edge1=project.selected_sewing_edge1,
                        point1=project.selected_sewing_point1,
                        edge2=hover_object,
                        point2=self.click_pattern_point(context, hover_object))
                    project.selected_sewing_edge1 = None
                    project.selected_sewing_point1 = None
                    console.info("sewing", sw)
                    if sw is None:
                        reason = project.last_sewing_error or "sewing overlap!"

                        def draw(self, context):
                            self.layout.label(text=reason)

                        context.window_manager.popup_menu(draw, title="Cannot add sewing",
                                                          icon='ERROR')
                        return {"CANCELLED"}
                    self.select_created_sewing(project, sw)
        elif self.mode == "CANCEL":
            project.selected_sewing_edge1 = None
            project.selected_sewing_point1 = None
        context.area.tag_redraw()
        return {"FINISHED"}

    def click_pattern_point(self, context, edge):
        """The click position in the pattern space of the edge.

        The pointer position comes from the preselection gizmo, which is also
        what decides which edge is hovered - so the point and the edge always
        belong to the same mouse event. The operator's own copy of the location
        is only a fallback.
        """
        manager = global_data.temp_draw_manager
        location = None
        if manager is not None and manager.mouse_location is not None:
            location = manager.mouse_location
        else:
            location = self.origin_mouse_location
        view_position = region2view_coord(context, location)
        point = edge.pattern.view_to_pattern_pos(view_position)
        # Printed so a wrong direction can be traced: the fraction says which
        # end of the edge the click was near, and the two fractions of a sewing
        # decide whether the second half is flipped.
        fraction = edge_click_fraction(edge, point)
        console.info("sewing click", f"edge={edge.global_uuid}", f"fraction={fraction:.3f}",
                     "near first" if fraction < 0.5 else "near second")
        return point

    @staticmethod
    def select_created_sewing(project, sewing):
        """Select the sewing that was just created, so it is obvious and editable."""
        _clear_selection(project.selected_sewings)
        for side in (sewing.side1, sewing.side2):
            update_selection_cache(project.selected_sewings, side, "SET", True)
        # edge = hover_object = context.scene.qmyi.hover_object
        # project = get_active_node_tree(context)
        # if project.selected_sewing_edge1 is None:
        #     project.selected_sewing_edge1 = edge
        #     return
        # context.window.cursor_modal_set("CROSSHAIR")
        # context.window_manager.modal_handler_add(self)
        # self.draw_manager: TempDrawManager = global_data.temp_draw_manager
        # self.draw_manager.clear()
        # p1state = self.register_state(ClickState())
        # p2state = self.register_state(ClickState())
        # self.define_transition(p1state, p2state)
        # #
        # def cb1(_self, _context):
        #     console.info("cb1")
        #     hover_object = _context.scene.qmyi.hover_object
        #     if hover_object is not None and hover_object.global_uuid != -1 and isinstance(hover_object, Edge2D):
        #         self.edge1 = hover_object
        #         console.info(hover_object)
        #         _self.state_result = StateResultType.SUCCESS
        # def cb2(_self, _context):
        #     console.info("cb2")
        #     hover_object = _context.scene.qmyi.hover_object
        #     if hover_object is not None and hover_object.global_uuid != -1 and isinstance(hover_object, Edge2D):
        #         self.edge2 = hover_object
        #         console.info(hover_object)
        #         _self.state_result = StateResultType.SUCCESS
        #
        # p1state.data_change_cb.append(cb1)
        # p2state.data_change_cb.append(cb2)


register, unregister = register_classes_factory((NODE_OT_add_sewing_1to1,))
