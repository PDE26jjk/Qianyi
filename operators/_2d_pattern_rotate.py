import math
import bpy
import numpy as np
from bpy.props import FloatVectorProperty, BoolProperty, FloatProperty
from bpy.types import Context
from bpy.utils import register_classes_factory
from mathutils import Vector, Matrix
import gpu
from gpu_extras.batch import batch_for_shader
from utilities.console import console
from ._2d_operator_base import Operator2DBase
from .states.IState import IState
from .states.PointSelectionState import PointPickState
from .states.StatefulOperator import StateOperator, ReturnState
from .. import global_data
from ..declarations import Operators
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_pattern_rotate(Operator2DBase, StateOperator):
    bl_idname = Operators.PatternRotate2D
    bl_label = "pattern rotate"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}
    pivot_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initial_mouse_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initial_angle: FloatProperty(default=0.0, options={"SKIP_SAVE"})
    initialized_angle: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        if not context.scene.qmyi.edit_mode == "PATTERN":
            return False
        project = get_active_node_tree(context)
        if project is not None:
            if len(project.selected_patterns) > 0:
                return True
        return False

    def setup_state_machine(self, context):
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        self.project = get_active_node_tree(context)
        self.origin_pattern_data = {}
        self.current_mouse_location = (0.0, 0.0)
        self.draw_handler = None
        # ================= State 1: 选取旋转中心 =================
        # p1state = self.register_state(PointPickState())
        self.initialized_pivot = True

        # def cb_pivot(_self, _context):
        #     co = region2view_coord(context, _self.point_position)
        #     if not self.initialized_pivot:
        #         self.initialized_pivot = True
        #         self.pivot_location = co
        #         # 进入旋转状态后启动绘制虚线的回调
        #         self.setup_draw_handler(context)
        #         return

        # p1state.data_change_cb.append(cb_pivot)
        # ================= State 2: 旋转版片 =================
        p2state = self.register_state(PointPickState())

        self.initialized_angle = False

        def cb_rotate(_self, _context):
            co = region2view_coord(context, _self.point_position)
            self.current_mouse_location = co
            if not self.initialized_angle:
                self.initialized_angle = True
                self.initial_mouse_location = co
                # 记录所有选中版片的初始状态
                self.origin_pattern_data = {}
                for item in self.project.selected_patterns:
                    if item.uuid != -1:
                        obj = global_data.get_obj_by_uuid(item.uuid, check_uuid=False)
                        if obj:
                            self.origin_pattern_data[item.uuid] = {
                                'pattern': obj,
                                'anchor': list(obj.anchor),
                                'rotation': obj.rotation
                            }
                center = np.array((0, 0), dtype=np.float32)
                for uuid, orig_data in self.origin_pattern_data.items():
                    obj = orig_data['pattern']
                    # center += obj.anchor
                    center += obj.pattern_to_view_pos(obj.center)
                self.pivot_location = center / len(self.origin_pattern_data)
                # 计算鼠标相对于旋转中心的初始角度
                dx = self.initial_mouse_location[0] - self.pivot_location[0]
                dy = self.initial_mouse_location[1] - self.pivot_location[1]
                self.initial_angle = math.atan2(dy, dx)
                self.setup_draw_handler(context)
                return
            # 计算当前鼠标的角度和增量旋转角
            dx = co[0] - self.pivot_location[0]
            dy = co[1] - self.pivot_location[1]
            current_angle = math.atan2(dy, dx)
            delta_angle = current_angle - self.initial_angle
            # 计算用于平移锚点的旋转矩阵
            cos_a = math.cos(delta_angle)
            sin_a = math.sin(delta_angle)
            rot_mat = Matrix((
                (cos_a, -sin_a, 0),
                (sin_a, cos_a, 0),
                (0, 0, 1)
            ))
            pivot_vec = Vector((self.pivot_location[0], self.pivot_location[1], 0))
            for uuid, orig_data in self.origin_pattern_data.items():
                obj = orig_data['pattern']
                orig_anchor = Vector((orig_data['anchor'][0], orig_data['anchor'][1], 0))
                # 旋转锚点：先将锚点移到以pivot为原点的坐标系，旋转，再移回
                new_anchor = rot_mat @ (orig_anchor - pivot_vec) + pivot_vec
                obj.anchor = (new_anchor.x, new_anchor.y)
                obj.rotation = orig_data['rotation'] + delta_angle
            context.area.tag_redraw()

        p2state.data_change_cb.append(cb_rotate)
        # self.define_transition(p1state, p2state)

    def setup_draw_handler(self, context):
        """注册3D视图绘制回调以绘制虚线"""
        if self.draw_handler is not None:
            return
        self.draw_handler = bpy.types.SpaceNodeEditor.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_VIEW'
        )

    def draw_callback(self, context):
        """绘制从旋转中心到鼠标位置的虚线"""
        if not self.initialized_pivot or not self.initialized_angle:
            return
        pivot = self.pivot_location
        mouse = self.current_mouse_location
        p1 = Vector((pivot[0], pivot[1], 0))
        p2 = Vector((mouse[0], mouse[1], 0))
        dist = (p2 - p1).length
        if dist < 0.001:
            return
        direction = (p2 - p1).normalized()
        # 生成虚线段
        dash_len = 6
        gap_len = 4
        step = dash_len + gap_len
        points = []
        current_dist = 0
        while current_dist < dist:
            start_p = p1 + direction * current_dist
            end_dist = min(current_dist + dash_len, dist)
            end_p = p1 + direction * end_dist
            points.append(start_p)
            points.append(end_p)
            current_dist += step
        if len(points) < 2:
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        # 设置虚线颜色为白色
        shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
        batch = batch_for_shader(shader, 'LINES', {"pos": points})
        batch.draw(shader)

    def remove_draw_handler(self):
        """移除绘制回调"""
        if self.draw_handler is not None:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self.draw_handler, 'WINDOW')
            self.draw_handler = None

    def handle_failure(self, context, state: IState):
        """操作取消时，恢复所有版片到初始状态"""
        if self.initialized_angle:
            for uuid, orig_data in self.origin_pattern_data.items():
                obj = orig_data['pattern']
                obj.anchor = orig_data['anchor']
                obj.rotation = orig_data['rotation']
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        """结束操作，清理回调并刷新视图"""
        self.remove_draw_handler()
        context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_pattern_rotate,))
