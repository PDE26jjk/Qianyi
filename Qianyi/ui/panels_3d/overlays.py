"""Overlay controls for the 3D viewport.

The overlays themselves live in `gizmos/view3d_overlay.py`; everything here is
the scene state they read, so the panel only has to expose it.
"""

import bpy

from ... import declarations
from . import VIEW_3D_PT_qmyi_base


class QY_PT_view3d_overlays(VIEW_3D_PT_qmyi_base):
    bl_category = "Qianyi"
    bl_label = "Overlays"
    bl_idname = declarations.Panels.View3DOverlays
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        qmyi = context.scene.qmyi

        col = layout.column(align=True)
        col.label(text="Vertex Colors")
        col.prop(qmyi, "view3d_vertex_colors", expand=True)
        if qmyi.view3d_vertex_colors != 'OFF':
            col.label(text="drawn over Blender's own shading", icon='INFO')

        box = layout.box()
        box.prop(qmyi, "view3d_seams", toggle=True)
        sub = box.column()
        sub.enabled = qmyi.view3d_seams
        sub.prop(qmyi, "view3d_seam_width")

        layout.prop(qmyi, "view3d_hud", toggle=True)
        layout.label(text="hidden with Blender's overlays", icon='INFO')


classes = (QY_PT_view3d_overlays,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
