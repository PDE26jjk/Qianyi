"""Silhouette guide controls, under the Projects panel.

The guide projects a collection of objects into the pattern window as an
alignment background (see `gizmos/silhouette_guide.py`). Everything here is
display state on the project - one collection, one projection - so the controls
belong with the project, not with the pattern tools.
"""

import bpy
from bpy.types import Context

from ...declarations import Panels
from ...utilities.node_tree import get_active_node_tree
from . import NODE_PT_qmyi_base


class QY_PT_silhouette(NODE_PT_qmyi_base):
    bl_category = "Project"
    bl_parent_id = Panels.Projects
    bl_label = "Silhouette"
    bl_idname = Panels.Silhouette
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    def draw(self, context: Context):
        layout = self.layout
        project = get_active_node_tree(context)
        if project is None:
            return

        layout.prop(project, "show_silhouette", toggle=True)

        col = layout.column()
        col.enabled = project.show_silhouette
        col.prop(project, "silhouette_collection", text="")
        if project.silhouette_collection is None:
            col.label(text="pick the collection to project", icon='INFO')
        col.prop(project, "silhouette_axis")
        col.prop(project, "silhouette_offset")
        col.separator()
        col.prop(project, "silhouette_color")
        col.prop(project, "silhouette_opacity")
        col.prop(project, "silhouette_show_mesh")
        row = col.row()
        row.enabled = project.silhouette_show_mesh
        row.prop(project, "silhouette_mesh_opacity")
        col.label(text="1:1 with the pattern, in millimetres", icon='DRIVER_DISTANCE')


classes = (QY_PT_silhouette,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
