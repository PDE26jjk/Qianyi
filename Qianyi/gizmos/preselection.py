import bpy
import gpu
from bpy.types import Gizmo, GizmoGroup

from ..utilities.console import console
from . import TempDrawManager
from ..utilities.node_tree import get_active_node_tree
from .. import global_data
from ..declarations import Gizmos, GizmoGroups


class NODE_GGT_qmyi_preselection(GizmoGroup):
    bl_idname = GizmoGroups.Preselection
    bl_label = "preselection ggt"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "WINDOW"
    bl_options = {"SELECT"}

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def setup(self, context):
        self.gizmo = self.gizmos.new(NODE_GT_qmyi_preselection.bl_idname)


class NODE_GT_qmyi_preselection(Gizmo):
    bl_idname = Gizmos.Preselection

    __slots__ = ()

    def draw(self, context):
        pass

    def test_select(self, context, location):
        qmyi = context.scene.qmyi
        if qmyi is None or len(global_data.temp_data) == 0:
            bpy.context.workspace.status_text_set(
                f"Qianyi Not initiated!")
            raise Exception("Qianyi is not initiated!")
        mouse_x, mouse_y = location
        # res = context.region.view2d.region_to_view(mouse_x, mouse_y)
        draw_manager: TempDrawManager = global_data.temp_draw_manager
        # The preview of the sewing that would be created needs the pointer
        # position to know which end of the second edge is being pointed at.
        draw_manager.mouse_location = (mouse_x, mouse_y)
        id_texture = draw_manager.id_texture
        if id_texture is None:
            return -1
        with id_texture.bind():
            fb = gpu.state.active_framebuffer_get()
            buffer = fb.read_color(mouse_x, mouse_y, 1, 1, 4, 0, "FLOAT")
        # r, g, b, a = buffer[0][0]
        uuid = draw_manager.rgb_to_index(*buffer[0][0])

        old_hover_obj = qmyi.hover_object
        obj = None
        if uuid != 255:
            # What the pass drew at this id: the pair of a pattern and one of its
            # elements. An edge serves a whole instance chain, so the element
            # alone cannot say which member the pointer is over - the pick is the
            # only record that can, and the selection turns it into the active
            # pattern.
            picked = draw_manager.resolve(uuid)
            if picked is not None:
                pattern, kind, obj = picked
                draw_manager.hover_pick = (pattern, kind, obj)
            else:
                obj = global_data.get_obj_by_uuid(uuid, False)
                draw_manager.hover_pick = None
        else:
            draw_manager.hover_pick = None
        # console_print("uuid" ,uuid,obj.global_uuid)
        if old_hover_obj != obj:
            qmyi.set_hover_object(obj)
            context.area.tag_redraw()
        # bpy.context.workspace.status_text_set(f"test_select {mouse_x, mouse_y,}, uuid: {uuid},obj:{qmyi.hover_object}")

        return -1
