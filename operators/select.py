import bpy
from bpy.types import Operator, Context
from bpy.props import IntProperty, BoolProperty, EnumProperty
from bpy.utils import register_classes_factory

from ..utilities.node_tree import get_active_node_tree
from .. import global_data
from ..declarations import Operators

mode_property = EnumProperty(
    name="Mode",
    items=[
        ("SET", "Set", "Set new selection", "SELECT_SET", 1),
        ("EXTEND", "Extend", "Add to existing selection", "SELECT_EXTEND", 2),
        (
            "SUBTRACT",
            "Subtract",
            "Subtract from existing selection",
            "SELECT_SUBTRACT",
            3,
        ),
        ("TOGGLE", "Toggle", "Toggle selection", "RADIOBUT_OFF", 4),
    ],
)


def update_selection_cache(collection, target_obj, mode, is_replace_mode):
    """
    通用选择逻辑处理器
    :param collection: bpy_prop_collection (selected_vertices 或 selected_edges)
    :param target_obj: 实际的对象 (Vertex2D 或 Edge2D)
    :param mode: 操作模式 (TOGGLE, ADD, SUBTRACT)
    :param is_replace_mode: 是否是替换模式 (即没有按 Shift/Ctrl)
    """

    uuid = target_obj.get_temp_data()['uuid']
    found_index = -1
    for i, item in enumerate(collection):
        if item.uuid == uuid:
            found_index = i
            break

    # 3. 计算目标状态
    should_select = True
    if mode == "SUBTRACT":
        should_select = False
    elif mode == "TOGGLE":
        should_select = not target_obj.is_selected
    elif is_replace_mode:
        should_select = True
    # EXTEND 默认为 True

    # 4. 执行状态更新
    # A. 更新物体自身的布尔值 (用于绘制高亮)
    target_obj.is_selected = should_select

    # B. 更新缓存列表
    if should_select:
        if found_index == -1:
            item = collection.add()
            item.uuid = target_obj.global_uuid
    else:
        if found_index != -1:
            collection.remove(found_index)

    return should_select


def _clear_selection(collection):
    for item in collection:
        if item.uuid != -1:
            obj = global_data.get_obj_by_uuid(item.uuid, check_uuid=False)
            if obj:
                obj.is_selected = False
    collection.clear()


class NODE_OT_qmyi_select(Operator):
    bl_idname = Operators.Select
    bl_label = "Select Entities"
    bl_options = {"UNDO", "REGISTER"}

    # index: IntProperty(name="Index", default=-1)
    mode: mode_property

    @classmethod
    def poll(cls, context: 'Context'):
        return get_active_node_tree(context) is not None

    def execute(self, context: Context):
        qmyi = context.scene.qmyi

        hit = qmyi.hover_object is not None and qmyi.hover_object.global_uuid != -1
        if hit and not hasattr(qmyi.hover_object, "is_selected"):
            return {"CANCELLED"}  # 或者 PASS_THROUGH
        mode = self.mode
        edit_mode = qmyi.edit_mode
        hover_object = qmyi.hover_object
        project = get_active_node_tree(context)

        is_replace = (mode not in {"EXTEND", "SUBTRACT", "TOGGLE"})
        if is_replace:
            if edit_mode == "PATTERN":
                _clear_selection(project.selected_patterns)
            elif edit_mode == "EDGE":
                _clear_selection(project.selected_vertices)
                _clear_selection(project.selected_edges)
            elif edit_mode == "SEWING":
                _clear_selection(project.selected_sewings)
        if hit:
            # 针对 PATTERN 模式
            if edit_mode == "PATTERN":
                update_selection_cache(project.selected_patterns, hover_object, mode, is_replace)
                if hover_object.is_selected:
                    for i, p in enumerate(project.patterns):
                        # print(i,p)
                        if p == hover_object:
                            project.active_pattern_index = i
                            break

            elif edit_mode == "EDGE":
                type_name = type(hover_object).__name__

                if "Vertex" in type_name:
                    update_selection_cache(project.selected_vertices, hover_object, mode, is_replace)

                elif "Edge" in type_name:
                    update_selection_cache(project.selected_edges, hover_object, mode, is_replace)
            elif edit_mode == "SEWING":
                update_selection_cache(project.selected_sewings, hover_object, mode, is_replace)

        context.area.tag_redraw()
        return {"FINISHED"}

register, unregister = register_classes_factory(
    (
        NODE_OT_qmyi_select,

    )
)
