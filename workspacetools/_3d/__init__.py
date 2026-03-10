import bpy
from bpy.utils import register_tool, unregister_tool

from .pick_mesh import VIEW3D_T_qmyi_pick_mesh

tools = (
    (VIEW3D_T_qmyi_pick_mesh, {"separator": True, "group": False}),
)


def register():
    for tool in tools:
        register_tool(tool[0], **tool[1])


def unregister():
    for tool in reversed(tools):
        unregister_tool(tool[0])
