"""The Qianyi panel the UV editor carries.

The reset control lives where the UV is seen - the UV editor's sidebar - and
acts on the active object, so which pattern it resets is the one being looked
at. The panel also carries the scene's UV scale, the number a seeded or reset
UV is multiplied by, so it can be tuned while the layer it sizes is on screen.
"""

from bpy.types import Panel

from ...declarations import Operators, Panels


class IMAGE_PT_qmyi_pattern_uv(Panel):
    # The UV editor is the image editor (its space id is IMAGE_EDITOR), working
    # in its UV mode; there is no 'IMAGE' space type to register against.
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Qianyi"
    bl_label = "Pattern UV"
    bl_idname = Panels.PatternUV

    @classmethod
    def poll(cls, context):
        # The UV editor is the image editor working in its UV mode; the panel is
        # offered there and not while the same space shows a plain image. A
        # version that does not name the mode still gets the panel.
        mode = getattr(getattr(context, "space_data", None), "mode", None)
        return mode is None or mode == 'UV'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.qmyi, "uv_scale")
        obj = context.active_object
        props = getattr(obj, "qmyi_simulation_props", None)
        if props is not None and props.is_pattern_mesh:
            layout.operator(Operators.ResetPatternUV, icon='LOOP_BACK')
        else:
            layout.label(text="select a pattern mesh", icon='INFO')
