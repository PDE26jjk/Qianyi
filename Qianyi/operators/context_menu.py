import bpy
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty, IntProperty
from bpy.types import Operator, Context, Event, PropertyGroup


from ..declarations import Operators


class NODE_OT_qmyi_context_menu(Operator):
    """Show element's settings"""

    bl_idname = Operators.ContextMenu
    bl_label = "Qianyi Context Menu"

    type: StringProperty(name="Type", options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})
    delayed: BoolProperty(default=False)

    @classmethod
    def description(cls, context: Context, properties: PropertyGroup):
        return cls.__doc__

    def invoke(self, context: Context, event: Event):
        if not self.delayed:
            return self.execute(context)

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if event.value == "RELEASE":
            return self.execute(context)

        return {"RUNNING_MODAL"}

    def execute(self, context: Context):
        qmyi = context.scene.qmyi
        def draw_context_menu(self, context: Context):
            col = self.layout.column()
            col.label(text="transform",)
            row = col.row()
            row.operator(Operators.PatternMove2D, text="move")
            col = self.layout.column()
            col.label(text="instance",)
            row = col.row()
            if qmyi.edit_mode == "PATTERN":
                row.operator(Operators.PatternCopyInstance, text="copy instance")
                row.operator(Operators.PatternCopyInstance, text="copy instance mirror").mirror = True
            if qmyi.edit_mode == "EDGE":
                col = self.layout.column()
                col.label(text="edge",)
                row = col.row()
                # Named explicitly: the operator asks for Blender's redo panel
                # once it has run, and only the invoke path does that. A popup
                # menu's default call context is not something to rely on here.
                row.operator_context = 'INVOKE_DEFAULT'
                row.operator(Operators.DivideEdge2D, text="divide")
                row = col.row()
                row.operator_context = 'INVOKE_DEFAULT'
                row.operator(Operators.Corner2D, text="round").mode = "ROUND"
                row.operator(Operators.Corner2D, text="chamfer").mode = "CHAMFER"
                row.operator(Operators.Corner2D, text="hollow").mode = "CONCAVE"

        # if not element:
        #     bpy.ops.wm.call_menu(name="NODE_MT_selected_menu")
        #     return {"FINISHED"}

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


register, unregister = register_classes_factory((NODE_OT_qmyi_context_menu,))
