# code: GLM 5.1
# review: TODO
import time

import bpy, gpu
import numpy as np
from bpy.types import Operator, Context, Event
from bpy.utils import register_classes_factory
from mathutils import Vector
from gpu_extras.batch import batch_for_shader

from utilities.console import console
from ..utilities.node_tree import get_active_node_tree
from .. import global_data
from ..declarations import Operators
from .select import mode_property, update_selection_cache, _clear_selection


# ───────────────────────── 辅助函数 ─────────────────────────
def get_start_dist(value1, value2, invert: bool = False):
    """返回较小/较大的起始值和跨度"""
    values = [value1, value2]
    values.sort(reverse=invert)
    start = values[0]
    return int(start), int(abs(value2 - value1))


def generate_dashed_points(p1, p2, dash_len=6, gap_len=4):
    """
    在两点之间生成虚线顶点对 (用于 GL_LINES 模式)
    :param p1: 起点 Vector
    :param p2: 终点 Vector
    :param dash_len: 实线段长度 (像素)
    :param gap_len: 间隙长度 (像素)
    :return: [(x,y), (x,y), ...] 顶点列表
    """
    points = []
    direction = p2 - p1
    length = direction.length
    if length < 1e-6:
        return points
    dir_n = direction.normalized()
    current = 0.0
    while current < length:
        seg_start = p1 + dir_n * current
        seg_end_dist = min(current + dash_len, length)
        seg_end = p1 + dir_n * seg_end_dist
        points.append((seg_start.x, seg_start.y))
        points.append((seg_end.x, seg_end.y))
        current += dash_len + gap_len
    return points


# ───────────────────────── 绘制回调 ─────────────────────────
def draw_callback_px(self, context):
    """绘制虚线边框 + 半透明填充的选区矩形"""
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    start = self.start_coords
    end = self.mouse_pos
    # ── 1. 半透明填充 (TRI_FAN) ──
    fill_verts = (
        (start.x, start.y),
        (end.x, start.y),
        (end.x, end.y),
        (start.x, end.y),
    )
    fill_batch = batch_for_shader(shader, "TRI_FAN", {"pos": fill_verts})
    shader.bind()
    shader.uniform_float("color", (0.3, 0.5, 0.85, 0.12))
    fill_batch.draw(shader)
    # ── 2. 虚线边框 (LINES) ──
    gpu.state.line_width_set(1.5)
    border_color = (0.4, 0.6, 1.0, 0.75)
    corners = [
        (start, Vector((end.x, start.y))),  # 下边
        (Vector((end.x, start.y)), end),  # 右边
        (end, Vector((start.x, end.y))),  # 上边
        (Vector((start.x, end.y)), start),  # 左边
    ]
    for p1, p2 in corners:
        dash_pts = generate_dashed_points(p1, p2, dash_len=6, gap_len=4)
        if len(dash_pts) >= 2:
            dash_batch = batch_for_shader(shader, "LINES", {"pos": dash_pts})
            shader.bind()
            shader.uniform_float("color", border_color)
            dash_batch.draw(shader)
    # ── 恢复 OpenGL 默认值 ──
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


# ───────────────────────── 框选操作器 ─────────────────────────
class NODE_OT_qmyi_select_box(Operator):
    """通过拖拽矩形框选实体"""
    bl_idname = Operators.SelectBox
    bl_label = "Box Select"
    bl_options = {"UNDO", "REGISTER"}
    mode: mode_property
    _handle = None

    @classmethod
    def poll(cls, context: 'Context'):
        return get_active_node_tree(context) is not None

    # ── Invoke: 进入模态 ──
    def invoke(self, context: Context, event: Event):
        self.start_coords = Vector((event.mouse_region_x, event.mouse_region_y))
        self.mouse_pos = self.start_coords
        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)
        args = (self, context)
        self._handle = bpy.types.SpaceNodeEditor.draw_handler_add(
            draw_callback_px, args, "WINDOW", "POST_PIXEL"
        )
        return {"RUNNING_MODAL"}

    # ── Main: 框选核心逻辑 ──
    def main(self, context: Context):
        draw_manager = global_data.temp_draw_manager
        id_texture = draw_manager.id_texture
        if id_texture is None:
            return False
        start_x, width = get_start_dist(self.start_coords.x, self.end_coords.x)
        start_y, height = get_start_dist(self.start_coords.y, self.end_coords.y)
        if not width or not height:
            return False
        # ── 读取 ID 纹理区域 ──
        start_time = time.time()
        with id_texture.bind():
            fb = gpu.state.active_framebuffer_get()
            buffer = fb.read_color(start_x, start_y, width, height, 4, 0, "FLOAT")
        # # ── 收集框内所有唯一 UUID ──
        # unique_uuids = set()
        # buffer.dimensions = (width * height, 4)
        # for pixel in buffer:
        #     uuid = draw_manager.rgb_to_index(pixel[0], pixel[1], pixel[2], pixel[3])
        #     if uuid not in (-1, 255):
        #         unique_uuids.add(uuid)
        # console.info(unique_uuids)

        buffer.dimensions = (4 , width * height)
        N = width * height
        flat = np.array(buffer, dtype=np.float32).ravel()

        if len(flat) == N * 4:
            r = flat[0:N]
            g = flat[N:2 * N]
            b = flat[2 * N:3 * N]
            a = flat[3 * N:4 * N]
            pixels = np.stack([r, g, b, a], axis=-1)  # shape 变为 (N, 4)
        else:
            pixels = flat.reshape(-1, 4)

        rgba_255 = (pixels * 255.0).round().astype(np.uint32)
        uuids_uint = (rgba_255[:, 0] << 24) | (rgba_255[:, 1] << 16) | (rgba_255[:, 2] << 8) | rgba_255[:, 3]
        uuids_int = uuids_uint.astype(np.int32)
        valid_mask = (uuids_int != -1) & (uuids_int != 255)
        unique_uuids = set(np.unique(uuids_int[valid_mask]))
        # console.info(unique_uuids)
        # console.info("time: ",(time.time() - start_time) * 1000)
        # ── 选择状态处理 ──
        qmyi = context.scene.qmyi
        edit_mode = qmyi.edit_mode
        project = get_active_node_tree(context)
        mode = self.mode
        is_replace = (mode not in {"EXTEND", "SUBTRACT", "TOGGLE"})
        # SET 模式先清空已有选择
        if is_replace:
            if edit_mode == "PATTERN":
                _clear_selection(project.selected_patterns)
            elif edit_mode == "EDGE":
                _clear_selection(project.selected_vertices)
                _clear_selection(project.selected_edges)
            elif edit_mode == "SEWING":
                _clear_selection(project.selected_sewings)
        # ── 逐个更新框内实体的选择状态 ──
        for uuid in unique_uuids:
            obj = global_data.get_obj_by_uuid(uuid, check_uuid=False)
            if obj is None or not hasattr(obj, "is_selected"):
                continue
            if edit_mode == "PATTERN":
                update_selection_cache(
                    project.selected_patterns, obj, mode, is_replace
                )
                if obj.is_selected:
                    for i, p in enumerate(project.patterns):
                        if p == obj:
                            project.active_pattern_index = i
                            break
            elif edit_mode == "EDGE":
                type_name = type(obj).__name__
                if "Vertex" in type_name:
                    update_selection_cache(
                        project.selected_vertices, obj, mode, is_replace
                    )
                elif "Edge" in type_name:
                    update_selection_cache(
                        project.selected_edges, obj, mode, is_replace
                    )
            elif edit_mode == "SEWING":
                update_selection_cache(
                    project.selected_sewings, obj, mode, is_replace
                )
        context.area.tag_redraw()
        return True

    # ── Modal: 处理鼠标事件 ──
    def modal(self, context: Context, event: Event):
        if event.type in ("RIGHTMOUSE", "ESC"):
            return self.end(context, False)
        if event.type == "MOUSEMOVE":
            context.area.tag_redraw()
            self.mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        if event.type == "LEFTMOUSE":
            self.end_coords = Vector((event.mouse_region_x, event.mouse_region_y))
            return self.end(context, self.main(context))
        return {"RUNNING_MODAL"}

    # ── End: 清理并退出 ──
    def end(self, context, succeede):
        context.window.cursor_modal_restore()
        if self._handle is not None:
            bpy.types.SpaceNodeEditor.draw_handler_remove(
                self._handle, "WINDOW"
            )
        retval = {"FINISHED"} if succeede else {"CANCELLED"}
        context.area.tag_redraw()
        return retval


register, unregister = register_classes_factory((NODE_OT_qmyi_select_box,))
