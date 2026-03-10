import bpy
from bpy.types import Operator
from bpy.utils import register_classes_factory

from utilities.console import console_print
from .. import global_data
from ..utilities.node_tree import get_active_node_tree
from ..declarations import Operators, Panels


def update_fabrics_global_uuid_map(project):
    for f in project.fabrics:
        f.get_temp_data()
        global_data.uuid2obj[f.global_uuid] = f


class QY_OT_AddFabric(bpy.types.Operator):
    bl_idname = Operators.AddFabric
    bl_label = "Add Fabric"
    bl_description = "Add this fabric from the project"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        index = len(project.fabrics)
        project.fabrics.add()
        project.fabrics[index].name = "Fabric_" + str(index)
        update_fabrics_global_uuid_map(project)

        context.area.tag_redraw()
        return {"FINISHED"}


class QY_OT_RemoveFabric(bpy.types.Operator):
    bl_idname = Operators.RemoveFabric
    bl_label = "Remove Fabric"
    bl_description = "Removes this fabric from the project"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        index = project.active_fabric_index
        if len(project.fabrics) <= 1:
            return {"CANCELLED"}
        if index < len(project.fabrics):
            project.fabrics.remove(index)
            update_fabrics_global_uuid_map(project)
            if index >= len(project.fabrics):
                project.active_fabric_index = len(project.fabrics) - 1
        else:
            return {"CANCELLED"}

        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class QY_OT_MoveFabric(bpy.types.Operator):
    bl_idname = Operators.ChangeFabricOrder
    bl_label = "Change Fabric Order"
    bl_description = "Moves this fabric in the list"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    move_up: bpy.props.IntProperty(options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        index = project.active_fabric_index
        if index < len(project.fabrics):
            next_step = 1 if not self.move_up else -1
            next_index = (index + next_step) % len(project.fabrics)
            project.fabrics.move(index, next_index)
            # move() only swap memory, we must modify global map by hand.

            update_fabrics_global_uuid_map(project)
            project.active_fabric_index = next_index
        else:
            return {"CANCELLED"}

        return {"FINISHED"}


register, unregister = register_classes_factory((QY_OT_AddFabric, QY_OT_RemoveFabric, QY_OT_MoveFabric))
