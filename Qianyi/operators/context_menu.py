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
            # One command per line. A row of buttons moves the menu's item cursor
            # to its own last button, which puts everything drawn after it
            # sideways; an aligned column holds that cursor, but makes the menu as
            # wide as the editor. What groups commands instead is a menu of its
            # own - the corner modes are one.
            layout = self.layout
            if qmyi.edit_mode == "PATTERN":
                layout.label(text="transform", )
                layout.operator(Operators.PatternMove2D, text="move")
                layout.label(text="instance", )
                layout.operator(Operators.PatternCopyInstance, text="copy instance")
                layout.operator(Operators.PatternCopyInstance,
                                text="copy instance mirror").mirror = True
            if qmyi.edit_mode == "EDGE":
                layout.label(text="edge",)
                # Named explicitly: the operator asks for Blender's redo panel
                # once it has run, and only the invoke path does that. A popup
                # menu's default call context is not something to rely on here.
                layout.operator_context = 'INVOKE_DEFAULT'
                layout.operator(Operators.DivideEdge2D, text="divide")
                layout.menu("NODE_MT_qmyi_corner", text="corner")
                layout.operator_context = 'EXEC_DEFAULT'
                layout.label(text="point",)
                layout.operator(Operators.MergeConnected2D, text="merge connected")
                layout.operator(Operators.ElementsDelete2D, text="delete")
            if qmyi.edit_mode == "SEWING":
                layout.label(text="sewing",)
                # The halves the selection names, or the half under the pointer:
                # a right click on a half is enough to turn it round.
                layout.operator(Operators.SewingReverse2D, text="reverse the half")

        # if not element:
        #     bpy.ops.wm.call_menu(name="NODE_MT_selected_menu")
        #     return {"FINISHED"}

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


register, unregister = register_classes_factory((NODE_OT_qmyi_context_menu,))
