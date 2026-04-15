from typing import Optional, List

import bpy

from .console import console_print
from ..declarations import Panels
import ctypes


def get_active_node_tree(context) -> Optional['QianyiProject']:
    space = context.space_data
    if space and hasattr(space, 'node_tree') and space.node_tree:
        if space.node_tree.bl_idname == Panels.QianyiNodeTree:
            return space.node_tree
    return None


def set_active_node_tree(context, node_tree):
    space = context.space_data
    if space and space.tree_type and space.tree_type == Panels.QianyiNodeTree:
        space.node_tree = node_tree


def get_all_node_tree() -> List['QianyiProject']:
    return [
        ngroup for ngroup in bpy.data.node_groups
        if ngroup.bl_idname == Panels.QianyiNodeTree
    ]


def redraw_node_editors():
    for area in bpy.context.screen.areas:
        if area.type == 'NODE_EDITOR':
            area.tag_redraw()


def change_node_editors_zoom_limit_unsafe(context, minzoom=0.01, maxzoom=10):
    for area in context.screen.areas:
        if area.type == 'NODE_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    pointer = region.view2d.as_pointer()
                    # print(pointer)
                    offset = {"minzoom": 24, "maxzoom": 25}  # struct View2D in DNA_view2d_types.h
                    v2d_floats = (ctypes.c_float * 50).from_address(pointer)
                    # print(v2d_floats[offset["minzoom"]])
                    v2d_floats[offset["minzoom"]] = minzoom
                    v2d_floats[offset["maxzoom"]] = maxzoom
