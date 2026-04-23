import bpy

from .registration import register_full, unregister_full

bl_info = {
    "name": "Qianyi",
    "author": "PDE26jjk",
    "version": (0, 0, 1),
    "blender": (4, 3, 0),
    "location": "View3D > Toolbar",
    "description": "Fabric simulation, garment design",
    "warning": "Experimental",
    "category": "3D View",
}


def register():
    register_full()


def unregister():
    unregister_full()