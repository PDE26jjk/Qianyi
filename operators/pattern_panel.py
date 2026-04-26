import bpy
from bpy.types import Operator
from bpy.utils import register_classes_factory

from utilities.console import console_print
from .. import global_data
from ..utilities.node_tree import get_active_node_tree
from ..declarations import Operators, Panels


def update_patterns_global_uuid_map(project):
    for p in project.patterns:
        # console_print("p uuid ",p.global_uuid)
        global_data.uuid2obj[p.global_uuid] = p


class QY_OT_RemovePattern(bpy.types.Operator):
    bl_idname = Operators.RemovePattern
    bl_label = "Remove Pattern"
    bl_description = "Removes this pattern from the project"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        index = project.active_pattern_index
        if index < len(project.patterns):
            project.remove_patterns([project.patterns[index]])
            # project.patterns.remove(index)
            # update_patterns_global_uuid_map(project)
            if index >= len(project.patterns):
                project.active_pattern_index = len(project.patterns) - 1
        else:
            return {"CANCELLED"}

        # for k in global_data.uuid2obj.keys():
        #     if k != global_data.uuid2obj[k].global_uuid:
        #         console_print(k, global_data.uuid2obj[k].global_uuid, index,type(global_data.uuid2obj[k]))
        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class QY_OT_MovePattern(bpy.types.Operator):
    bl_idname = Operators.ChangePatternOrder
    bl_label = "Change Pattern Order"
    bl_description = "Moves this pattern in the list"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    move_up: bpy.props.IntProperty(options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        index = project.active_pattern_index
        if index < len(project.patterns):
            next_step = 1 if not self.move_up else -1
            next_index = (index + next_step) % len(project.patterns)
            project.patterns.move(index, next_index)
            # move() only swap memory, we must modify global map by hand.
            # if not abs(index - next_index) > 1:
            #     p1, p2 = project.patterns[index], project.patterns[next_index]
            #     global_data.uuid2obj[p1.global_uuid], global_data.uuid2obj[p2.global_uuid] = p1, p2
            # else:
            #     update_patterns_global_uuid_map(project)
            project.refresh_patterns()
            project.active_pattern_index = next_index
        else:
            return {"CANCELLED"}

        return {"FINISHED"}


register, unregister = register_classes_factory((QY_OT_RemovePattern, QY_OT_MovePattern))
