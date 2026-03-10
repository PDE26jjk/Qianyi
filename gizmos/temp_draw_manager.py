import ctypes
import time
from typing import List

import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from .edit_gizmos import Point, Line, Rect
from .pattern_renderer import PatternRenderer
from ..utilities.coords_transform import create_2d_matrix
from .. import global_data
from ..model.geometry import Edge2D, Vertex2D
from ..model.pattern import Pattern
from ..utilities.node_tree import get_active_node_tree
from .GizmosMeshRenderer import MeshRenderer


class TempDrawManager:
    def __init__(self):
        self.points: List[Point] = []
        self.lines: List[Line] = []
        self.id_texture = None
        self.region_width = 0
        self.region_height = 0

    def add_point(self):
        self.points.append(Point())
        return self.points[-1]

    def add_line(self, point1=(0, 0), point2=(0, 0)):
        self.lines.append(Line())
        line = self.lines[-1]
        line.p1.x = point1[0]
        line.p1.y = point1[1]
        line.p2.x = point2[0]
        line.p2.y = point2[1]
        return line

    def add_Rect(self):
        return Rect(self)

    def clear(self):
        self.points = []
        self.lines = []

    @staticmethod
    def get_v2d_cur(region):
        pointer = region.view2d.as_pointer()
        v2d_floats = (ctypes.c_float * 8).from_address(pointer)
        xmin, xmax, ymin, ymax = v2d_floats[4:8]
        return np.array(((xmin, ymin), (xmax, ymax)))

    def draw_offscreen_thumbnail(self, offscreen, region, position='bottom_right', size=600, margin=10):
        """
        在指定区域绘制GPUOffScreen的缩略图

        参数:
        - offscreen: GPUOffScreen对象
        - region: 要绘制的区域
        - size: 缩略图大小（像素）
        - margin: 边距（像素）
        """
        # 获取区域尺寸
        region_width = region.width
        region_height = region.height
        sizex = size
        sizey = sizex / region_width * region_height
        if sizey > size:
            sizey = size
            sizex = sizey / region_height * region_width

        # 计算缩略图位置
        if position == 'bottom_right':
            x0 = region_width - sizex - margin
            y0 = margin
        elif position == 'bottom_left':
            x0 = margin
            y0 = margin
        elif position == 'top_right':
            x0 = region_width - sizex - margin
            y0 = region_height - sizey - margin
        elif position == 'top_left':
            x0 = margin
            y0 = region_height - sizex - margin
        else:
            x0 = region_width - sizey - margin
            y0 = margin

        x1 = x0 + sizex
        y1 = y0 + sizey

        cur = self.get_v2d_cur(region)
        pos = np.array(((x0, y0), (x1, y1)))
        pos = pos / np.array((region.width, region.height)) * (cur[1] - cur[0]) + cur[0]
        (x0, y0), (x1, y1) = pos
        # 创建绘制纹理的着色器
        shader = gpu.shader.from_builtin('IMAGE')

        # 创建矩形批次（使用标准化设备坐标）
        vertices = (
            (x0, y0), (x0, y1),
            (x1, y1), (x1, y0)
        )

        indices = ((0, 1, 2), (0, 2, 3))

        texcoords = (
            (0, 0), (0, 1),
            (1, 1), (1, 0)
        )

        batch = batch_for_shader(
            shader, 'TRIS',
            {
                "pos": vertices,
                "texCoord": texcoords,
            },
            indices=indices,
        )

        # 绑定纹理并绘制
        gpu.state.blend_set('ALPHA')
        shader.bind()
        shader.uniform_sampler("image", offscreen.texture_color)
        batch.draw(shader)
        gpu.state.blend_set('NONE')

    @staticmethod
    def index_to_rgb(i):
        r = ((i >> 24) & 0xFF) / 255.0
        g = ((i >> 16) & 0xFF) / 255.0
        b = ((i >> 8) & 0xFF) / 255.0
        a = (i & 0xFF) / 255.0
        return r, g, b, a

    @staticmethod
    def rgb_to_index(r, g, b, a):
        r = int(round(r * 255.0))
        g = int(round(g * 255.0))
        b = int(round(b * 255.0))
        a = int(round(a * 255.0))
        u = ((r << 24) | (g << 16) | (b << 8) | a)
        return ctypes.c_int32(u).value

    def draw_id(self, context, region_matrix):
        region = context.region
        # create offscreen
        width, height = region.width, region.height
        if self.region_width != width or self.region_height != height or self.id_texture is None:
            self.region_width = width
            self.region_height = height
            self.id_texture = gpu.types.GPUOffScreen(width, height, format="RGBA8")
        with self.id_texture.bind():
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(0.0, 0.0, 0.0, 1.0))
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')

            shader.bind()
            gpu.state.point_size_set(15.0)
            gpu.state.blend_set("NONE")
            node_tree = get_active_node_tree(context)
            qmyi = context.scene.qmyi
            if node_tree is not None:
                patterns = node_tree.patterns
                for p in patterns:
                    p: Pattern
                    if p.need_render_update:
                        p.update_render_points()
                        p.need_render_update = False
                    if qmyi.edit_mode == "PATTERN":
                        if p.mesh_renderer is not None:
                            p.mesh_renderer.draw_triangles(region_matrix, self.index_to_rgb(p.global_uuid), True)
                    elif qmyi.edit_mode == "EDGE":
                        for e in p.edges:
                            e: Edge2D
                            gpu.state.line_width_set(10.0)
                            shader.bind()
                            e.update(p)
                            shader.uniform_float("color", self.index_to_rgb(e.global_uuid))
                            render_points = []
                            render_points.extend(e.render_points + p.anchor)
                            line_batch = batch_for_shader(
                                shader, 'LINE_STRIP',
                                {"pos": render_points},
                            )
                            line_batch.draw(shader)

                        for v in p.vertices:
                            v: Vertex2D
                            v.get_temp_data()
                            # shader.bind()
                            shader.uniform_float("color", self.index_to_rgb(v.global_uuid))
                            point_batch = batch_for_shader(
                                shader, 'POINTS',
                                {"pos": [v.co + p.anchor, v.co + p.anchor]},
                            )
                            point_batch.draw(shader)

    def create_region_matrix(self, context, node_tree):
        region = context.region
        (xmin, ymin), (xmax, ymax) = self.get_v2d_cur(region)
        zoom = region.width / (xmax - xmin)
        ratio = region.height / region.width
        # zoom2 = region.height / (ymax - ymin)
        offset = -node_tree.view_center / (xmax - xmin) * 2.0  # why 2 ?
        offset[1] /= ratio
        return create_2d_matrix(scale=(zoom * ratio, zoom), offset=offset)

    def draw(self, context):
        node_tree = get_active_node_tree(context)
        if node_tree is None:
            return
        start_time = time.time()
        qmyi = context.scene.qmyi

        region_matrix = self.create_region_matrix(context, node_tree)
        region = context.region
        #     return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        if len(self.lines) > 0:
            coords = []
            for line in self.lines:
                coords.append(line.p1)
                coords.append(line.p2)

            # bpy.context.workspace.status_text_set(f"{len(self.lines)}{ coords}")
            rect_batch = batch_for_shader(
                shader, 'LINES',
                {"pos": coords}
            )

            shader.bind()
            shader.uniform_float("color", (0.2, 0.8, 0.2, 0.8))
            gpu.state.line_width_set(3.0)
            rect_batch.draw(shader)

        # bpy.context.workspace.status_text_set(f"{region_matrix}")
        patterns = node_tree.patterns
        shader.bind()
        gpu.state.line_width_set(1.0)
        for p in patterns:
            if p.need_render_update:
                p.update_render_points()
                p.update_render_vertex()
                p.need_render_update = False
                p.line_renderer = PatternRenderer(p)
                p.mesh_renderer = MeshRenderer(p)
            if p.line_renderer is None:
                p.line_renderer = PatternRenderer(p)
            if p.mesh_renderer is None and p.mesh_object is not None:
                p.mesh_renderer = MeshRenderer(p)
            if p.mesh_renderer is not None:
                if p.mesh_renderer.obj != p.mesh_object:
                    p.mesh_renderer.start_rendering(p.mesh_object)
                p.mesh_renderer.draw_lines(region_matrix, p.is_selected)


            gpu.state.blend_set("ALPHA")
            color = (0.2, 0.2, 0.8, 1)
            line_color = (*color[:3], color[3] * 0.8)  # 降低透明度
            shader.uniform_float("color", line_color)
            p.line_renderer.draw_edges(region_matrix, color=line_color)

            if qmyi.edit_mode == "EDGE":
                gpu.state.point_size_set(8.0)

                p.line_renderer.draw_vertices(region_matrix, color=(0.6, 0.6, 0.2, 1))



        # if qmyi.edit_mode == "EDGE" and len(qmyi.selected_objects) > 0:
        #     gpu.state.line_width_set(2.0)
        #     for obj in qmyi.selected_objects:
        #         # bpy.context.workspace.status_text_set(f"{obj}")
        #         if isinstance(obj, Edge2D):
        #             shader.uniform_float("color", (0.4, 0.4, 0.8, 1))
        #             render_points = []
        #             if obj.render_points is None:
        #                 # raise Exception(obj.get_temp_data(), global_data.temp_data)
        #                 continue
        #             render_points.extend(obj.render_points + obj.pattern.anchor)
        #             line_batch = batch_for_shader(
        #                 shader, 'LINE_STRIP',
        #                 {"pos": render_points},
        #             )
        #             line_batch.draw(shader)
        #         elif isinstance(obj, Vertex2D):
        #             v: Vertex2D = obj
        #             shader.uniform_float("color", (0.9, 0.9, 0.8, 1))
        #             point_batch = batch_for_shader(
        #                 shader, 'POINTS',
        #                 {"pos": [v.co, v.co]},
        #             )
        #             point_batch.draw(shader)
        sewings = node_tree.sewings
        gpu.state.line_width_set(5.0)
        for s in sewings:
            s.update()
            s.renderer.draw(region_matrix)

        self.draw_id(context, region_matrix)
        if qmyi.hover_object is not None and qmyi.hover_object.global_uuid != -1:
            gpu.matrix.push()

            obj = qmyi.hover_object
            offset = [0., 0.]
            if hasattr(obj,'pattern'):
                offset = obj.pattern.anchor
            elif hasattr(obj,'anchor'):
                offset = obj.anchor
            gpu.matrix.translate((offset[0], offset[1], 0.0))
            if isinstance(obj, Edge2D):
                shader.uniform_float("color", (1, 1, 1, 1))
                render_points = []
                if obj.render_points is None:
                    raise Exception(obj.get_temp_data(), global_data.temp_data)
                if obj.render_points is not None:
                    # raise Exception(obj.get_temp_data(), global_data.temp_data)
                    render_points.extend(obj.render_points)
                    line_batch = batch_for_shader(
                        shader, 'LINE_STRIP',
                        {"pos": render_points},
                    )
                    line_batch.draw(shader)
            elif isinstance(obj, Vertex2D):
                v: Vertex2D = obj
                shader.uniform_float("color", (1, 1, 1, 1))
                point_batch = batch_for_shader(
                    shader, 'POINTS',
                    {"pos": [v.co, v.co]},
                )
                point_batch.draw(shader)
            elif isinstance(obj, Pattern):
                p: Pattern = obj
                # console_print("hover pattern",p.global_uuid,p.global_idx,p.render_points)
                line_batch = batch_for_shader(
                    shader, 'LINE_LOOP',
                    {"pos": p.render_points},
                )
                gpu.state.blend_set("ALPHA")
                line_color = (0.8, 0.8, 0.8, 1)
                gpu.state.line_width_set(3.0)
                shader.uniform_float("color", line_color)
                line_batch.draw(shader)
            gpu.matrix.pop()

        self.draw_offscreen_thumbnail(self.id_texture, region)
        total_time = time.time() - start_time
        # bpy.context.workspace.status_text_set(f"total time: {total_time * 1000}")

    def __del__(self):
        if self.id_texture is not None:
            del self.id_texture
