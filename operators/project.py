import bpy
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..utilities.node_tree import change_node_editors_zoom_limit_unsafe
from ..declarations import Operators, Panels


def reassign_tree_indices():
    trees = [
        ngroup for ngroup in bpy.data.node_groups
        if ngroup.bl_idname == Panels.QianyiNodeTree
    ]
    if not trees:
        return []
    trees = sorted(trees, key=lambda t: t.index)
    for i, tree in enumerate(trees):
        tree.index = i
    return trees


class QY_OT_AddProject(Operator):
    bl_idname = Operators.AddProject
    bl_label = "GenerateAllMesh"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def execute(self, context):
        qmyi = context.scene.qmyi
        trees = reassign_tree_indices()

        curr_index = 0
        if qmyi.active_project_index < len(bpy.data.node_groups) and bpy.data.node_groups[
            qmyi.active_project_index].bl_idname == Panels.QianyiNodeTree:
            curr_index = bpy.data.node_groups[qmyi.active_project_index].index
            for i in range(curr_index + 1, len(trees)):
                trees[i].index += 1

        graph = bpy.data.node_groups.new("NodeTree", Panels.QianyiNodeTree)
        graph.index = curr_index - 1
        for i, group in enumerate(bpy.data.node_groups):
            if group == graph:
                qmyi.active_project_index = i
                break
        change_node_editors_zoom_limit_unsafe(context)
        return {"FINISHED"}


class QY_OT_RemoveProject(bpy.types.Operator):
    bl_idname = Operators.RemoveProject
    bl_label = "Remove Project"
    bl_description = "Removes this project from the file"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        active_project_index = context.scene.qmyi.active_project_index
        if active_project_index < len(bpy.data.node_groups):
            return bpy.data.node_groups[active_project_index].bl_idname == Panels.QianyiNodeTree
        return False

    def execute(self, context):
        qmyi = context.scene.qmyi
        group = bpy.data.node_groups[qmyi.active_project_index]
        removed_index = group.index
        bpy.data.node_groups.remove(group)

        trees = reassign_tree_indices()
        qmyi.active_project_index = 0
        if len(trees) > 0:
            # 尝试选择相同索引的项目
            new_index = min(removed_index, len(trees) - 1)

            # 找到该节点树在列表中的实际位置
            for i, tree in enumerate(bpy.data.node_groups):
                if tree == trees[new_index] and tree in trees:
                    qmyi.active_project_index = i
                    break

        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class QY_OT_MoveNodeTree(bpy.types.Operator):
    bl_idname = Operators.ChangeProjectOrder
    bl_label = "Change Project Order"
    bl_description = "Moves this project in the list"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    move_up: bpy.props.IntProperty(options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def poll(cls, context):
        active_project_index = context.scene.qmyi.active_project_index
        if active_project_index < len(bpy.data.node_groups):
            return bpy.data.node_groups[active_project_index].bl_idname == Panels.QianyiNodeTree
        return False

    def execute(self, context):
        trees = reassign_tree_indices()
        try:
            index = trees.index(bpy.data.node_groups[context.scene.qmyi.active_project_index])
            next_step = 1 if not self.move_up else -1
            next_index = (index + next_step) % len(trees)
            trees[index].index, trees[next_index].index = trees[next_index].index, trees[index].index
        except ValueError:
            return {'CANCELLED'}

        return {"FINISHED"}


register, unregister = register_classes_factory((QY_OT_AddProject, QY_OT_RemoveProject, QY_OT_MoveNodeTree))
