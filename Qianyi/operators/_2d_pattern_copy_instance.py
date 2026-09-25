import bpy
import numpy as np
from bpy.props import BoolProperty
from bpy.utils import register_classes_factory

from ..utilities.console import console
from ._2d_operator_base import Operator2DBase
from .states.PointSelectionState import PointPickState
from .states.StatefulOperator import StateOperator, ReturnState
from .. import global_data
from ..declarations import Operators
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_pattern_copy_instance(Operator2DBase, StateOperator):
    """copy pattern as instance"""
    bl_idname = Operators.PatternCopyInstance
    bl_label = "Copy as Instance/Mirror"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}

    mirror: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        if context.scene.qmyi.edit_mode != "PATTERN":
            return False
        project = get_active_node_tree(context)
        return project is not None and len(project.selected_patterns) > 0

    def setup_state_machine(self, context):
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)

        self.project = get_active_node_tree(context)
        self.source_pats = []
        for item in self.project.selected_patterns:
            if item.uuid != -1:
                pat = global_data.get_obj_by_uuid(item.uuid, check_uuid=False)
                if pat:
                    self.source_pats.append(pat)
        if not self.source_pats:
            self.return_state = ReturnState.CANCELLED
            return

        self.src_anchors = np.empty((len(self.source_pats), 2), dtype=np.float32)
        self.pats_renderers = []
        for idx, pat in enumerate(self.source_pats):
            self.src_anchors[idx] = pat.anchor[:]
            self.pats_renderers.append(pat.line_renderer)

        start_point = (0.0, 1e-6)
        self.origin_mouse_location = start_point
        self.initialized = False

        self._draw_handler = bpy.types.SpaceNodeEditor.draw_handler_add(
            self._draw_preview, (context,), 'WINDOW', 'POST_VIEW')

        # 鼠标交互
        p1state = self.register_state(PointPickState())

        self.new_anchors = None

        def on_mouse(_self, _context):
            co = region2view_coord(context, _self.point_position)
            if not self.initialized:
                self.initialized = True
                self.origin_mouse_location = co
                return
            offset = np.array((co[0] - self.origin_mouse_location[0],
                               co[1] - self.origin_mouse_location[1]))
            self.new_anchors = self.src_anchors + offset
            _context.area.tag_redraw()

        p1state.data_change_cb.append(on_mouse)

    def _draw_preview(self, context):
        if self.new_anchors is not None:
            for renderer, new_anchor in zip(self.pats_renderers, self.new_anchors):
                mirror_x = renderer.pattern.is_mirror ^ self.mirror
                renderer.draw_instance_edges(
                    anchor=new_anchor,
                    rotation=renderer.pattern.rotation,  # 或从源板片直接取 rotation
                    mirror=mirror_x
                )

    def handle_success(self, context, state):
        for src, new_anchor in zip(self.source_pats, self.new_anchors):
            # The copy itself lives in the model layer, so the script surface
            # and this operator produce the same pattern.
            new_pat = src.copy_pattern(as_instance=True, mirror=self.mirror,
                                       anchor=new_anchor)
            console.info(f"{src.name} -> {new_pat.name}")

        self.return_state = ReturnState.FINISHED

    def handle_failure(self, context, state):
        self.return_state = ReturnState.CANCELLED

    def fini(self, context):
        if hasattr(self, '_draw_handler') and self._draw_handler:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self._draw_handler, 'WINDOW')
        context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_pattern_copy_instance,))
