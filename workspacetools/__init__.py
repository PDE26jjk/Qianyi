import bpy
from bpy.utils import register_tool, unregister_tool

from .add_poly import NODE_T_qmyi_add_poly
from .select import NODE_T_qmyi_select
from ._3d import register as register_3d_tool
from ._3d import unregister as unregister_3d_tool


tools = (
    (NODE_T_qmyi_select, {"separator": True, "group": False}),
    (NODE_T_qmyi_add_poly, {"separator": True, "group": False}),
)

def register():
    if bpy.app.background:
        return

    for tool in tools:
        register_tool(tool[0], **tool[1])
    register_3d_tool()

def unregister():
    if bpy.app.background:
        return

    for tool in reversed(tools):
        unregister_tool(tool[0])
    unregister_3d_tool()
