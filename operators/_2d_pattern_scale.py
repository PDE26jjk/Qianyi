import math
import bpy
import numpy as np
from bpy.props import FloatVectorProperty, FloatProperty
from bpy.types import Context
from bpy.utils import register_classes_factory
from mathutils import Vector
import gpu
from gpu_extras.batch import batch_for_shader
from ._2d_operator_base import Operator2DBase
from .states.PointSelectionState import PointPickState
from .states.StatefulOperator import StateOperator, ReturnState
from .. import global_data
from ..declarations import Operators
from ..model.pattern_instance import collect_unique_instances
from ..utilities.coords_transform import region2view_coord
from ..utilities.node_tree import get_active_node_tree


class NODE_OT_pattern_scale(Operator2DBase, StateOperator):
    bl_idname = Operators.PatternScale2D
    bl_label = "pattern scale"
    bl_options = {'BLOCKING', 'GRAB_CURSOR', 'REGISTER', 'UNDO'}
    pivot_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initial_mouse_location: FloatVectorProperty(size=2, default=(0.0, 0.0), options={"SKIP_SAVE"})
    initial_dist: FloatProperty(default=1.0, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context: Context):
        if not context.scene.qmyi.edit_mode == "PATTERN":
            return False
        project = get_active_node_tree(context)
        if project is not None:
            return len(project.selected_patterns) > 0
        return False

    def setup_state_machine(self, context):
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        self.project = get_active_node_tree(context)
        self.current_mouse_location = (0.0, 0.0)
        self.current_scale_factor = 1.0
        self.draw_handler = None
        # 1. 收集选中的版片
        self.pattern_set = set()
        self.selected_uuids = set()
        for item in self.project.selected_patterns:
            if item.uuid != -1:
                pat = global_data.get_obj_by_uuid(item.uuid, check_uuid=False)
                if pat:
                    self.pattern_set.add(pat)
                    self.selected_uuids.add(pat.global_uuid)
        if not self.pattern_set:
            self.return_state = ReturnState.CANCELLED
            return
        # 获取所有关联的实例
        self.pattern_set = collect_unique_instances(self.pattern_set)
        # 2. 计算缩放中心 (所有选中版片锚点的均值)
        center = np.array((0, 0), dtype=np.float32)
        for p in self.pattern_set:
            for ins in p.instances:
                if ins.global_uuid in self.selected_uuids:
                    center += ins.pattern_to_view_pos(ins.center)
        self.pivot_location = center / len(self.selected_uuids)
        # 3. 设置状态机
        p1state = self.register_state(PointPickState())
        self.initialized = False

        def cb_scale(_self, _context):
            co = region2view_coord(context, _self.point_position)
            self.current_mouse_location = co
            if not self.initialized:
                self.initialized = True
                self.initial_mouse_location = co
                dx = co[0] - self.pivot_location[0]
                dy = co[1] - self.pivot_location[1]
                self.initial_dist = math.sqrt(dx * dx + dy * dy)
                if self.initial_dist < 1e-5:
                    self.initial_dist = 1e-5
                self.setup_draw_handler(context)
                return
            dx = co[0] - self.pivot_location[0]
            dy = co[1] - self.pivot_location[1]
            current_dist = math.sqrt(dx * dx + dy * dy)
            self.current_scale_factor = current_dist / self.initial_dist
            _context.area.tag_redraw()

        p1state.data_change_cb.append(cb_scale)

    def setup_draw_handler(self, context):
        if self.draw_handler is not None:
            return
        self.draw_handler = bpy.types.SpaceNodeEditor.draw_handler_add(
            self.draw_callback, (context,), 'WINDOW', 'POST_VIEW')

    def draw_callback(self, context):
        if not self.initialized:
            return
        # 1. 绘制虚线
        pivot = self.pivot_location
        mouse = self.current_mouse_location
        p1 = Vector((pivot[0], pivot[1], 0))
        p2 = Vector((mouse[0], mouse[1], 0))
        dist = (p2 - p1).length
        if dist > 0.001:
            direction = (p2 - p1).normalized()
            dash_len, gap_len = 6, 4
            step = dash_len + gap_len
            points_line = []
            current_dist = 0
            while current_dist < dist:
                start_p = p1 + direction * current_dist
                end_dist = min(current_dist + dash_len, dist)
                end_p = p1 + direction * end_dist
                points_line.append(start_p)
                points_line.append(end_p)
                current_dist += step
            if len(points_line) >= 2:
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                shader.bind()
                shader.uniform_float("color", (1.0, 1.0, 1.0, 0.5))
                batch = batch_for_shader(shader, 'LINES', {"pos": points_line})
                batch.draw(shader)
        # 2. 绘制缩放预览轮廓
        s = self.current_scale_factor
        pivot_location = Vector(self.pivot_location)
        for p in self.pattern_set:
            for ins in p.instances:
                if ins.global_uuid in self.selected_uuids:
                    orig_anchor = Vector(ins.anchor)
                    new_anchor = pivot_location + (orig_anchor - pivot_location) * s
                    color = (0.0, 1.0, 1.0, 1.0)
                else:
                    new_anchor = ins.anchor
                    color = (0.3, 0.6, 0.1, 1.0)
                ins.line_renderer.draw_instance_edges(
                    anchor=new_anchor,
                    rotation=ins.rotation,
                    mirror=ins.is_mirror,
                    scale=(s, s),
                    color=color,
                    thickness=2.0
                )

    def remove_draw_handler(self):
        if self.draw_handler is not None:
            bpy.types.SpaceNodeEditor.draw_handler_remove(self.draw_handler, 'WINDOW')
            self.draw_handler = None

    def handle_success(self, context, state):
        s = self.current_scale_factor
        # 确认时，直接获取当前顶点数据乘上缩放系数，并更新所有实例
        pivot_location = Vector(self.pivot_location)
        for p in self.pattern_set:
            for ins in p.instances:
                # TODO scale on center or anchor?
                # 如果是被选中的版片，更新锚点位置
                if ins.global_uuid in self.selected_uuids:
                    orig_anchor = Vector(ins.anchor)
                    new_anchor = pivot_location + (orig_anchor - pivot_location) * s
                    ins.anchor = new_anchor
                # 应用缩放到本地顶点
                for v in ins.vertices:
                    v.co = (v.co[0] * s, v.co[1] * s)
                for e in ins.edges:
                    e.handle1.co = (e.handle1.co[0] * s, e.handle1.co[1] * s)
                    e.handle2.co = (e.handle2.co[0] * s, e.handle2.co[1] * s)
                    for sp in e.spline_points:
                        sp.co = (sp.co[0] * s, sp.co[1] * s)
                ins.create_sections()
                ins.forced_update()
                ins.generate_mesh()
        self.return_state = ReturnState.FINISHED

    def handle_failure(self, context, state):
        # 预览阶段没有修改任何数据，直接取消即可
        self.return_state = ReturnState.CANCELLED

    def fini(self, context: Context):
        self.remove_draw_handler()
        context.area.tag_redraw()


register, unregister = register_classes_factory((NODE_OT_pattern_scale,))