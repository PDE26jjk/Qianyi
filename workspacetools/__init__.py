import bpy
from bpy.utils import register_tool, unregister_tool

from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree
from .add_poly import NODE_T_qmyi_add_poly
from .select import NODE_T_qmyi_select
from ._3d import register as register_3d_tool
from ._3d import unregister as unregister_3d_tool
from bl_ui.space_toolsystem_toolbar import NODE_PT_tools_active
from bl_ui.space_toolsystem_common import ToolDef

tools = (
    (NODE_T_qmyi_select, {"separator": True, "group": False}),
    (NODE_T_qmyi_add_poly, {"separator": True, "group": False}),
)
_original_tools_from_context = None
@classmethod
def filtered_tools_from_context(cls, context, mode=None):
    tree_type = getattr(context.space_data, 'tree_type', None) if context.space_data else None
    if tree_type != 'QianyiNodeTree':
        for tool in _original_tools_from_context.__func__(cls, context, mode):
            if tool is not None:
                item = tool
                if isinstance(tool, tuple):
                    item = tool[0]
                if hasattr(item, 'idname'):
                    item = item.idname
                # console.info("item", item)
                if 'qmyi.' in item:
                    continue
            yield tool
        return
    # yield from _original_tools_from_context.__func__(cls, context, mode)
    # return
    if mode is None:
        mode = tree_type
    # console.info("mode", mode)
    if not get_active_node_tree(context):
        yield None
        return
    if mode is None:
        if context.space_data is None:
            mode = None
        else:
            mode = context.space_data.tree_type
    qmyi_tools = []
    for tools in (cls._tools[None], cls._tools.get(mode, ())):
        for item in tools:
            if type(item) is ToolDef and 'qmyi.' in item.idname:
                qmyi_tools.append(item)
            # if not (type(item) is ToolDef) and callable(item):
            #     console.info("tool1", item)
            #     # yield from item(context)
            # else:
            #     console.info("tool2", item)
            #     # yield item

    # console.info("qmyi_tools", qmyi_tools)
    # yield tuple(qmyi_tools)
    for tools in qmyi_tools:
        yield tools
        yield None
    return
    result = []

def register():
    global _original_tools_from_context
    if bpy.app.background:
        return

    for tool in tools:
        register_tool(tool[0], **tool[1])
    register_3d_tool()
    if _original_tools_from_context is None:
        _original_tools_from_context = NODE_PT_tools_active.tools_from_context
    assert _original_tools_from_context != filtered_tools_from_context, \
        "_original_tools_from_context == filtered_tools_from_context"
    NODE_PT_tools_active.tools_from_context = filtered_tools_from_context

def unregister():
    global _original_tools_from_context
    if bpy.app.background:
        return

    for tool in reversed(tools):
        unregister_tool(tool[0])
    unregister_3d_tool()
    NODE_PT_tools_active.tools_from_context = _original_tools_from_context
    _original_tools_from_context = None
