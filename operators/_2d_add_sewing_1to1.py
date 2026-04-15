from bpy.props import FloatVectorProperty, BoolProperty, EnumProperty
from bpy.types import Context
from bpy.utils import register_classes_factory

from utilities.console import console
from ._2d_operator_base import Operator2DBase
from ..declarations import Operators
from ..model.geometry import Edge2D
from ..utilities.node_tree import get_active_node_tree

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
                else:
                    sw = project.add_sewing1to1(edge1=project.selected_sewing_edge1, edge2=hover_object)
                    project.selected_sewing_edge1 = None
                    console.info("sewing", sw)
                    if sw is None:
                        def draw(self, context):
                            self.layout.label(text="sewing overlap!")

                        context.window_manager.popup_menu(draw, title="Error", icon='ERROR')
                        return {"CANCELLED"}
        elif self.mode == "CANCEL":
            project.selected_sewing_edge1 = None
        context.area.tag_redraw()
        return {"FINISHED"}
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
