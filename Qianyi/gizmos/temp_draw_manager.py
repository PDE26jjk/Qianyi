import ctypes
import time
from typing import List

import gpu
import bpy
import numpy as np
from gpu_extras.batch import batch_for_shader

from .color_points_renderer import MultiColorPointsRenderer
from ..model.sewing import SewingOneSide
from ..model.qianyi_project import QianyiProject, edge_point_at, sewing_half_directions
from ..utilities.console import console
from .edit_gizmos import Point, Line, Rect
from .moving_curve import MovingCurve, MovingCurveWhole
from .pattern_renderer import PatternRenderer
from .points_renderer import PointsRenderer
from ..utilities.coords_transform import create_2d_matrix, region2view_coord
from .. import global_data
from ..model.geometry import Edge2D, Vertex2D
from ..model.model_data import owner_pattern
from ..model.pattern import Pattern
from ..utilities.node_tree import get_active_node_tree
from .GizmosMeshRenderer import MeshRenderer
from .silhouette_guide import SilhouetteGuide


INVALID_PATTERN_COLOR = (1.0, 0.25, 0.2, 1.0)
# A selected pattern is outlined a second time, thicker and in this colour: in
# every display mode other than "mesh" the ordinary outline is the same white
# for all patterns, which makes a selection impossible to read.
SELECTED_PATTERN_COLOR = (1.0, 0.62, 0.12, 1.0)
SELECTED_PATTERN_LINE_WIDTH = 3.0
# A selected edge or vertex, and the alpha the same element is drawn with while
# its own mode is not the active one.
SELECTED_EDGE_COLOR = (1.0, 1.0, 0.0, 1.0)
SELECTED_VERTEX_COLOR = (1.0, 1.0, 0.0, 1.0)
DIMMED_SELECTION_ALPHA = 0.35


def handles_visible(edge) -> bool:
    """Whether an edge's handles are drawn - and so also pickable.

    The edge is selected, or one of the points it owns is: a handle and a spline
    point are moved through the handles of the edge they belong to, so selecting
    one of them has to keep that edge's handles on screen. Asking only the edge
    left them undrawn the moment the click moved the selection onto a point, so
    the second handle of a corner could not be picked any more.
    """
    if edge.is_selected:
        return True
    for point in (*edge.handles, *edge.spline_points):  # loop: this edge's points
        if point.is_selected:
            return True
    return False


# The point a tool would act on, drawn under the pointer while the tool is
# active: the same idea as the add-vertex tool's preview, for the tools that
# pick a point of the outline instead of an edge.
TOOL_POINT_COLOR = (0.2, 1.0, 1.0, 1.0)
TOOL_PIVOT_COLOR = (1.0, 0.55, 0.1, 1.0)
TOOL_TARGET_COLOR = (0.3, 1.0, 0.3, 1.0)
TOOL_LINE_COLOR = (1.0, 0.65, 0.15, 0.9)


def dimmed_selection_color(color):
    """`color` at the alpha a selection of another mode is drawn with."""
    return (color[0], color[1], color[2], DIMMED_SELECTION_ALPHA)


def fabric_fill_color(pattern, alpha=0.5):
    """The fill colour of a pattern: its fabric's display colour, or a neutral grey.

    Display only - the fabric's colour is not part of the simulation payload.
    """
    try:
        fabric = pattern.fabric
    except Exception:
        fabric = None
    rgb = tuple(fabric.color) if fabric is not None else (0.85, 0.85, 0.9)
    return (rgb[0], rgb[1], rgb[2], alpha)


class TempDrawManager:
    def __init__(self):
        self.last_edit_mode = None
        self.points: List[Point] = []
        self.lines: List[Line] = []
        self.moving_curves: List[MovingCurve] = []
        self.id_texture = None
        self.region_width = 0
        self.region_height = 0
        self.mouse_location = None
        # Points a tool wants drawn: (pattern uuid, point in that pattern's space).
        self.tool_points = []
        # The tool that drew them: a preview belongs to the tool that made it, and
        # switching tools has to take it off the screen, which nothing else does.
        self.tool_owner = ""
        # Line segments a tool wants drawn, in view space.
        self.tool_lines: List[Line] = []
        # One polyline a tool wants drawn, in view space: a whole outline is one
        # batch this way instead of a segment per pair of samples.
        self.tool_polyline = None
        # Set while a tool's modal gesture owns the preview: the tool's own
        # cursor preview then leaves it alone.
        self.preview_locked = False
        # What the id pass drew, id by id: the pair of a pattern and one of its
        # elements. An edge is shared by every member of its chain, so the pass
        # draws it once per member and each draw carries that member's own id -
        # the pair is what a pick reads back, and an element on its own never
        # says which member was under the pointer.
        self.pick_of_id = {}
        # (pattern, kind, element) under the pointer, as of the last id pass the
        # pointer read; "kind" is "edge", "vertex", "spline_point", "handle1" or
        # "handle2". A tool that reacts to a click reads it here, and the
        # selection turns it into the active pattern.
        self.hover_pick = None
        # Projection of the project's silhouette objects, drawn behind the
        # patterns. Built lazily: a GPU shader cannot be created before the draw
        # callback has a context.
        self.silhouette_guide = None

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

    def add_moving_curve_whole(self, edge):
        self.moving_curves.append(MovingCurveWhole(edge))
        return self.moving_curves[-1]

    def add_moving_curve(self, edge):
        self.moving_curves.append(MovingCurve(edge))
        return self.moving_curves[-1]

    def clear(self):
        self.points.clear()
        self.lines.clear()
        self.moving_curves.clear()
        self.tool_points.clear()
        self.tool_lines.clear()
        self.tool_polyline = None

    @staticmethod
    def active_tool_id() -> str:
        """The id of the tool the node editor has active, or "" if unknown."""
        try:
            return getattr(bpy.context.workspace.tools.from_space_node(), "idname", "") or ""
        except Exception:
            return ""

    def set_tool_points(self, entries) -> None:
        """Show the points a tool is working with.

        `entries` is a list of ``(pattern, point, kind)``, where the kind picks
        the colour the point is drawn in: ``"hover"`` for what a click would
        take, ``"pivot"`` and ``"target"`` for the points a gesture has taken.
        """
        self.tool_owner = self.active_tool_id()
        self.tool_points = [(pattern.global_uuid,
                             (float(point[0]), float(point[1])), kind)
                            for pattern, point, kind in entries if pattern is not None]

    def set_tool_point(self, pattern, point, kind="hover") -> None:
        """Show one point of a pattern as what the tool would act on."""
        if pattern is None or point is None:
            self.tool_points = []
            return
        self.set_tool_points([(pattern, point, kind)])

    def add_tool_line(self, point1, point2) -> None:
        """Add one view-space segment to the tool's own preview."""
        self.tool_owner = self.active_tool_id()
        line = Line()
        line.set_points(point1, point2)
        self.tool_lines.append(line)

    def clear_tool_preview(self) -> None:
        """Drop everything a tool drew: its points and its lines."""
        self.tool_points = []
        self.tool_lines.clear()
        self.tool_polyline = None

    def set_tool_polyline(self, points) -> None:
        """Show one polyline as the tool's preview, in view space."""
        self.tool_owner = self.active_tool_id()
        self.tool_polyline = [tuple(point) for point in points]

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

    def picked_pattern(self):
        """The pattern under the pointer, or None.

        A tool that has to know which member of a chain the pointer is over asks
        here, and the answer is what the id pass drew - a pattern and one of its
        elements are one pair there. Nothing asks an element which pattern it
        belongs to: an edge is shared by the whole chain, so that question has
        no single answer.
        """
        pick = self.hover_pick
        return pick[0] if pick is not None else None

    def draw_edge_for_pick(self, pattern, edge, renderer, width=10.0):
        """Draw one edge for one pattern, with the id that pattern gave the pair.

        An edge is drawn once per member of its chain, each with that member's
        transform and its own id, so the pointer reads back the member it is
        over instead of whichever member happened to be drawn last.
        """
        own = pattern.pick_id("edge", edge)
        self.pick_of_id[own] = (pattern, "edge", edge.global_uuid)
        renderer.draw(self.index_to_rgb(own), width, draw_id=True, pattern=pattern)

    def resolve(self, index):
        """What the last id pass drew at one id: (pattern, kind, element).

        None when the id is not one this pass drew - the field behind a pattern,
        or a value left over from an older pass.
        """
        entry = self.pick_of_id.get(index)
        if entry is None:
            return None
        pattern, kind, element_uuid = entry
        element = global_data.get_obj_by_uuid(element_uuid, False)
        if element is None:
            return None
        return pattern, kind, element

    uniform_color_shader = None

    def draw_id(self, context):
        region = context.region
        # create offscreen
        width, height = region.width, region.height
        # One pass, one table: what a pick reads back is what this pass drew.
        self.pick_of_id = {}
        if self.region_width != width or self.region_height != height or self.id_texture is None:
            self.region_width = width
            self.region_height = height
            self.id_texture = gpu.types.GPUOffScreen(width, height, format="RGBA8")
        with self.id_texture.bind():
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(0.0, 0.0, 0.0, 1.0))
            shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')

            shader.bind()
            gpu.state.point_size_set(15.0)
            gpu.state.blend_set("NONE")
            node_tree = get_active_node_tree(context)
            qmyi = context.scene.qmyi
            if node_tree is not None:
                patterns = node_tree.patterns
                points_renderer = MultiColorPointsRenderer()
                for p in patterns:
                    p: Pattern
                    if p.need_render_update:
                        # The pass needs the lines as they are to draw their
                        # ids; the flag stays set, because the draw that follows
                        # rebuilds the points and the spline points as well.
                        # Clearing it here left those two stale until the next
                        # unrelated edit.
                        p.update_render_line()
                    if qmyi.edit_mode == "PATTERN":
                        if p.mesh_renderer is not None:
                            p.mesh_renderer.draw_fill_mesh(self.index_to_rgb(p.global_uuid), True)
                    elif qmyi.edit_mode == "EDGE":
                        edges = [*p.edges, *(e for il in p.internal_lines for e in il.edges)]
                        for e in edges:
                            e: Edge2D
                            if e.renderer is None:
                                e.need_update_points = True
                                e.update()
                            self.draw_edge_for_pick(p, e, e.renderer, 10.)
                            if handles_visible(e):
                                handle_ids = []
                                for slot, (kind, handle_type) in enumerate(
                                        (("handle1", e.handle1_type),
                                         ("handle2", e.handle2_type))):
                                    if handle_type == "VECTOR":
                                        handle_ids.append(None)
                                        continue
                                    handle = e.handle1 if slot == 0 else e.handle2
                                    own = p.pick_id(kind, handle)
                                    self.pick_of_id[own] = (p, kind, handle.global_uuid)
                                    handle_ids.append(own)
                                e.renderer.draw_handles(
                                    self.index_to_rgb(handle_ids[0] if handle_ids[0]
                                                      is not None else e.global_uuid),
                                    10., draw_id=True, pattern=p,
                                    handle_ids=tuple(handle_ids))
                            for sp in e.spline_points:
                                sp.get_temp_data()
                                own = p.pick_id("spline_point", sp)
                                self.pick_of_id[own] = (p, "spline_point", sp.global_uuid)
                                points_renderer.add_point(p, sp, self.index_to_rgb(own))

                        for v in p.vertices:
                            v: Vertex2D
                            v.get_temp_data()
                            own = p.pick_id("vertex", v)
                            self.pick_of_id[own] = (p, "vertex", v.global_uuid)
                            points_renderer.add_point(p, v, self.index_to_rgb(own))
                    elif qmyi.edit_mode == "SEWING":
                        if qmyi.edit_sub_mode == "ADD_SEWING1":
                            edges = [*p.edges, *(e for il in p.internal_lines for e in il.edges)]
                            for e in edges:
                                self.draw_edge_for_pick(p, e, e.renderer, 10.)
                        else:
                            sewings = node_tree.sewings
                            gpu.state.line_width_set(10.0)
                            for s in sewings:
                                s.renderer.draw_id()
                points_renderer.draw(15.0, draw_id=True)

    def draw_sewing_direction_preview(self, context, project):
        """Show which ends would be stitched while the second edge is hovered.

        Only the two end connectors, computed with the same rule the created
        sewing is drawn with: a half-segment's polyline starts at the end its
        click chose, and the connectors join the two halves' starts and their
        two ends. That is what makes the preview show the sewing's direction.
        """
        shader = self.uniform_color_shader
        edge1 = project.selected_sewing_edge1
        hover = context.scene.qmyi.hover_object
        if shader is None or edge1 is None or not isinstance(hover, Edge2D):
            return
        if self.mouse_location is None:
            return
        point1 = project.selected_sewing_point1
        if point1 is None:
            return
        # The first side named its pattern when it was clicked; the second side is
        # the one under the pointer, which the id pass is the only thing that can
        # say - the edge is shared by the whole chain.
        pattern1 = project.selected_sewing_pattern1 or owner_pattern(edge1)
        pattern2 = self.picked_pattern() or owner_pattern(hover)
        if pattern1 is None or pattern2 is None:
            return
        if (hover.global_uuid == edge1.global_uuid
                and pattern1.global_uuid == pattern2.global_uuid):
            # The pointer is back on the edge the first click chose, on the same
            # member: that is not a second side, so there is nothing to join.
            # The same edge of *another* member is a seam - two instances sewn
            # to each other along the one edge they share - and it is drawn.
            return
        point2 = pattern2.view_to_pattern_pos(region2view_coord(context, self.mouse_location))
        first_half, second_half = sewing_half_directions(edge1, point1, hover, point2)
        start1, end1 = first_half[0], first_half[1]
        start2, end2 = second_half[0], second_half[1]
        positions = [
            pattern1.pattern_to_view_pos(edge_point_at(edge1, start1)),
            pattern2.pattern_to_view_pos(edge_point_at(hover, start2)),
            pattern1.pattern_to_view_pos(edge_point_at(edge1, end1)),
            pattern2.pattern_to_view_pos(edge_point_at(hover, end2)),
        ]
        shader.bind()
        gpu.state.blend_set("ALPHA")
        gpu.state.line_width_set(1.5)
        shader.uniform_float("color", (0.2, 0.8, 0.8, 1.0))
        batch_for_shader(shader, 'LINES', {"pos": positions}).draw(shader)

    def draw_hover(self, qmyi):
        """Highlight the object under the pointer."""
        shader = self.uniform_color_shader
        hover_object = qmyi.hover_object
        if hover_object is not None:
            try:
                hover_object.get_index()
            except Exception as e:
                console.error("hover_object is invalid! ", e)
                qmyi.set_hover_object(None)
                return
        if hover_object is not None and hover_object.global_uuid != -1:
            gpu.matrix.push()
            # The pop must happen on every exit: an unbalanced push leaves
            # Blender's GPU matrix stack broken for the rest of the frame, and
            # the next consumer - Blender's own gizmo drawing - then reads a
            # null matrix and takes the process down (crash in
            # gizmo_axis_draw -> GPU_matrix_translate_3f -> translate_m4).
            try:
                obj = qmyi.hover_object
                # offset = [0., 0.]
                # The pattern the pointer is over: the id pass recorded which
                # member drew it, which the element itself cannot say - an edge
                # is shared by its whole chain.
                p = self.picked_pattern()
                if p is None:
                    if hasattr(obj, 'anchor'):
                        # A pattern is drawn in its own space.
                        # offset = obj.anchor
                        p = obj
                    else:
                        # A geometry element is drawn in the space of the pattern
                        # that owns the Sketch it lives in.
                        p = owner_pattern(obj)
                if p is None:
                    if isinstance(obj, SewingOneSide):  # why false?
                        # if obj.__class__.__name__ == "SewingOneSide":
                        if obj.sewing is not None:
                            gpu.state.line_width_set(20.)
                            obj.sewing.renderer.draw(dashed_line=False)
                    return
                # gpu.matrix.translate((offset[0], offset[1], 0.0))
                gpu.matrix.load_matrix(p.calc_matrix())
                if isinstance(obj, Edge2D):
                    gpu.state.point_size_set(5.0)
                    # console.info("edge", obj)
                    # obj.renderer.draw((1, 1, 1, 1), 10)
                    shader.uniform_float("color", (1, 1, 1, 1))
                    render_points = []
                    if obj.render_points is None:
                        console.warning("hover edge has no render points: ", obj)
                        return
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
                    gpu.state.point_size_set(10.0)
                    point_batch = batch_for_shader(
                        shader, 'POINTS',
                        {"pos": [v.co, v.co]},
                    )
                    point_batch.draw(shader)
                elif isinstance(obj, Pattern):
                    p: Pattern = obj
                    line_batch = batch_for_shader(
                        shader, 'LINE_LOOP',
                        {"pos": p.render_points},
                    )
                    gpu.state.blend_set("ALPHA")
                    line_color = (0.8, 0.8, 0.8, 1)
                    gpu.state.line_width_set(3.0)
                    shader.uniform_float("color", line_color)
                    line_batch.draw(shader)
                # console.info("hover",obj)
            finally:
                gpu.matrix.pop()

    def draw(self, context):
        project: QianyiProject = get_active_node_tree(context)
        if project is None:
            return
        start_time = time.time()
        draw_start_time = start_time
        qmyi = context.scene.qmyi

        if self.tool_points or self.tool_lines or self.tool_polyline:
            active = self.active_tool_id()
            if active and self.tool_owner and active != self.tool_owner:
                # The preview on screen was drawn by a tool the editor no longer
                # has active: the tool that made it is not the one being used, so
                # nothing would ever replace or clear it.
                self.clear_tool_preview()

        if self.uniform_color_shader is None:
            self.uniform_color_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader = self.uniform_color_shader
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

        patterns = project.patterns
        # The silhouette is the background of the pattern window, so it is drawn
        # before anything the patterns draw.
        if global_data.renderers_enabled:
            if self.silhouette_guide is None:
                self.silhouette_guide = SilhouetteGuide()
            self.silhouette_guide.draw(context, project)
        for p in patterns:
            if global_data.get_obj_by_uuid(p.global_uuid) is None:
                console.warning(f'{p} is invalid, refreshing...')
                project.refresh_patterns()
                break
        # console.info("-------------------")
        # for p in project.patterns:

        # console.info(f"temp lines: {(time.time() - start_time) * 1000}")
        # start_time = time.time()

        display_mode = qmyi.pattern_display_mode
        # Whether the pattern selection is the active one: it is drawn dimmed in
        # every other mode. Read once, so the loop cannot depend on a branch
        # that a pattern without a mesh does not take.
        in_pattern_mode = qmyi.edit_mode == "PATTERN"

        shader.bind()
        gpu.state.line_width_set(1.0)
        for p in patterns:
            if not p.initialized:
                p.initialize()
            if p.need_render_update:
                p.update_render_line()
                p.update_render_vertex()
                p.update_render_spline_point()
                p.need_render_update = False
                # p.line_renderer = PatternRenderer(p)
                # p.mesh_renderer = MeshRenderer(p)
            # if p.line_renderer is None:
            #     p.line_renderer = PatternRenderer(p)
            # if p.mesh_renderer is None and p.mesh_object is not None:
            #     p.mesh_renderer = MeshRenderer(p)
            if p.mesh_renderer is not None:
                if p.mesh_renderer.obj != p.mesh_object:
                    p.mesh_renderer.start_rendering(p.mesh_object)
                is_selected = in_pattern_mode and p.is_selected
                # The display mode only chooses what is drawn: no branch here
                # resamples a pattern, rebuilds a mesh or touches a sewing.
                if display_mode == 'MESH':
                    p.mesh_renderer.draw_mesh_lines(
                        is_selected, dim=p.is_selected and not in_pattern_mode)
                elif display_mode in ('SOLID', 'STRESS', 'DEBUG'):
                    # Stress and debug need an applied frame; without one the
                    # pattern keeps the solid fill and the header says why.
                    if display_mode == 'SOLID' or not p.mesh_renderer.draw_fill_mesh_vertex_colors(display_mode):
                        p.mesh_renderer.draw_fill_mesh(fabric_fill_color(p))

            gpu.state.blend_set("ALPHA")
            color = (0.2, 0.2, 0.8, 1)
            line_color = (*color[:3], color[3] * 0.8)
            # An outline that crosses itself cannot become a sound mesh: the
            # sampler drops the triangles it cannot validate, so the pattern is
            # drawn in red and the crossing is marked until it is fixed.
            outline_color = INVALID_PATTERN_COLOR if p.is_invalid else line_color
            shader.uniform_float("color", outline_color)
            p.line_renderer.draw_edges(color=outline_color)
            if p.is_invalid and p.invalid_point is not None:
                p.line_renderer.draw_invalid_marker(p.invalid_point)
            for il in p.internal_lines:
                # Each member draws the one shared line, with its own transform:
                # the line belongs to the Sketch, so a copy shows it too.
                il.renderer.draw_edges(color=line_color, pattern=p)
            if p.is_selected:
                # A pattern selected in the pattern mode keeps its selection
                # outline in the other modes - dimmed, so the mode the user is
                # in is still the one that reads as active.
                selection_color = (SELECTED_PATTERN_COLOR if in_pattern_mode
                                   else dimmed_selection_color(SELECTED_PATTERN_COLOR))
                p.line_renderer.draw_edges(
                    color=selection_color,
                    thickness=(SELECTED_PATTERN_LINE_WIDTH if in_pattern_mode
                               else SELECTED_PATTERN_LINE_WIDTH - 1.0))
                # The next pattern draws its own lines; leave the width as the
                # loop set it.
                gpu.state.line_width_set(1.0)
            if qmyi.show_grain_dir:
                p.line_renderer.draw_grain_dir()

            if qmyi.edit_mode == "EDGE":
                gpu.state.point_size_set(8.0)

                p.line_renderer.draw_vertices(color=(0.6, 0.6, 0.2, 1))
                # for e in p.edges:
                #     e: Edge2D
                #     if e.renderer is None:
                #         e.need_update_points = True
                #         e.update()
                #     e.renderer.draw( (1,1,0,1), 10.)

        # console.info(f"main: {(time.time() - start_time) * 1000}")
        # start_time = time.time()

        # The selection belongs to the mode it was made in and outlives a mode
        # switch: here it is drawn in its own colour while its mode is active
        # and dimmed and thin while another mode is, so what is selected stays
        # readable and is still selected when its mode comes back.
        in_edge_mode = qmyi.edit_mode == "EDGE"
        points_renderer = PointsRenderer()
        dimmed_points_renderer = PointsRenderer()
        edge_selection_color = (SELECTED_EDGE_COLOR if in_edge_mode
                                else dimmed_selection_color(SELECTED_EDGE_COLOR))
        # The patterns that read each Sketch, in one pass over the project: an
        # element of a Sketch is on screen once per member of its chain, so the
        # highlight is drawn for each of them with that member's transform.
        members_of = {}
        for pattern in project.patterns:  # loop: one list per Sketch
            if pattern.sketch_uuid == -1:
                continue
            members_of.setdefault(int(pattern.sketch_uuid), []).append(pattern)
        for obj in project.get_selected_objects_by_mode("EDGE", strict=False):
            owner = owner_pattern(obj)
            members = members_of.get(int(owner.sketch_uuid), []) if owner is not None else []
            if isinstance(obj, Edge2D):
                for member in members:
                    obj.renderer.draw(edge_selection_color, 3 if in_edge_mode else 2,
                                      pattern=member)
                    if in_edge_mode:
                        obj.renderer.draw_handles((0, 1, 0, 1), 2, pattern=member)
            elif isinstance(obj, Vertex2D):
                for member in members:
                    if in_edge_mode:
                        points_renderer.add_point(member, obj)
                        # A handle or a control point is moved through the
                        # handles of the edge it belongs to, so they are drawn
                        # while it is selected - the handle itself shows what it
                        # is attached to instead of floating on its own.
                        parent = obj.get_parent()
                        if isinstance(parent, Edge2D) and in_edge_mode:
                            parent.renderer.draw_handles((0, 1, 0, 1), 2, pattern=member)
                    else:
                        dimmed_points_renderer.add_point(member, obj)
        if in_edge_mode and qmyi.edit_sub_mode in ("ADD_VERTEX", "ADD_SPLINE_POINT"):
            if project.nearest_point is not None:
                points_renderer.add_point(project.patterns[project.nearest_pattern], project.nearest_point)

        if qmyi.edit_mode == "SEWING":
            sewings = project.sewings
            gpu.state.line_width_set(5.0)
            for s in sewings:
                if self.last_edit_mode != qmyi.edit_mode:
                    s.need_render_update = True
                s.update()
                is_selected = s.side1.is_selected or s.side2.is_selected
                s.renderer.draw(dashed_line=is_selected)
            if qmyi.edit_sub_mode == "ADD_SEWING1":
                # console.info("edge1",project.selected_sewing_edge1)
                if project.selected_sewing_edge1 is not None:
                    # The highlight goes on the member the first click was made
                    # on: the edge is shared by its chain, and the chain's owner
                    # is not necessarily the pattern the pointer was over.
                    project.selected_sewing_edge1.renderer.draw(
                        color=(0.2, 0.8, 0.8, 1), thickness=10.0,
                        pattern=project.selected_sewing_pattern1)
                    self.draw_sewing_direction_preview(context, project)
        else:
            # The seams selected in the sewing mode are still selected here:
            # draw those chains dimmed instead of hiding them. The selection
            # holds the sides a seam was drawn with - that is what the pick
            # answers - so each entry is read as the seam it belongs to, and each
            # seam once however many of its sides are selected.
            selected_sewings = []
            seen_sewings = set()
            for side in project.get_selected_objects_by_mode("SEWING", strict=False):
                sewing = side.sewing
                if sewing is None or sewing.global_uuid in seen_sewings:
                    continue
                seen_sewings.add(sewing.global_uuid)
                selected_sewings.append(sewing)
            if selected_sewings and self.last_edit_mode != qmyi.edit_mode:
                for s in selected_sewings:
                    s.need_render_update = True
            gpu.state.line_width_set(3.0)
            for s in selected_sewings:
                s.update()
                s.renderer.draw(alpha=DIMMED_SELECTION_ALPHA)
        # console.info(f"mode_collect_points: {(time.time() - start_time) * 1000}")
        # start_time = time.time()
        if dimmed_points_renderer.points:
            dimmed_points_renderer.draw(dimmed_selection_color(SELECTED_VERTEX_COLOR), 10)
        points_renderer.draw(SELECTED_VERTEX_COLOR, 10)

        if self.tool_polyline and len(self.tool_polyline) > 1:
            # One polyline, one batch: an outline has a sample per few
            # millimetres and drawing it a segment at a time is what made the
            # preview slow.
            polyline_batch = batch_for_shader(
                shader, 'LINE_STRIP', {"pos": self.tool_polyline})
            shader.bind()
            shader.uniform_float("color", TOOL_LINE_COLOR)
            gpu.state.line_width_set(2.5)
            polyline_batch.draw(shader)

        if self.tool_lines:
            # The tool's own preview: the radius it is measuring, the arc it
            # would add. Drawn in its own colour so it is not mistaken for the
            # selection or for a pattern edge.
            coords = []
            for line in self.tool_lines:  # loop: one previewed segment per entry
                coords.append(line.p1)
                coords.append(line.p2)
            tool_batch = batch_for_shader(shader, 'LINES', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", TOOL_LINE_COLOR)
            gpu.state.line_width_set(2.5)
            tool_batch.draw(shader)

        if self.tool_points:
            # What the active tool would act on: drawn over the pattern so the
            # point a click lands on is visible before the click happens.
            for kind, color, size in (("hover", TOOL_POINT_COLOR, 12.0),
                                      ("pivot", TOOL_PIVOT_COLOR, 16.0),
                                      ("target", TOOL_TARGET_COLOR, 16.0)):
                # loop: one kind of tool point per pass
                chosen = [(uuid_value, point) for uuid_value, point, point_kind
                          in self.tool_points if point_kind == kind]
                if not chosen:
                    continue
                tool_renderer = PointsRenderer()
                for uuid_value, point in chosen:  # loop: one tool point
                    pattern = global_data.get_obj_by_uuid(uuid_value, check_uuid=False)
                    if pattern is not None:
                        tool_renderer.add_point(pattern, point)
                tool_renderer.draw(color, size)

        if self.moving_curves:
            for mc in self.moving_curves:
                # The handles come with the members: a drag that moves a handle
                # has to show it where each member is drawn, not only on the one
                # that owns the Sketch.
                mc.renderer.draw_instances((1, 1, 0, 1), 7, handles=True,
                                           handle_color=(0, 1, 0, 1))

        self.last_edit_mode = qmyi.edit_mode

        # console.info(f"mode: {(time.time() - start_time) * 1000}")
        # start_time = time.time()

        self.draw_hover(qmyi)
        # console.info(f"hover: {(time.time() - start_time) * 1000}")
        # start_time = time.time()

        self.draw_id(context)
        # console.info(f"id: {(time.time() - start_time) * 1000}")
        # start_time = time.time()
        region = context.region

        # self.draw_offscreen_thumbnail(self.id_texture, region)
        # console.info(f"thumbnail: {(time.time() - start_time) * 1000}")
        start_time = time.time()
        total_time = start_time - draw_start_time
        bpy.context.workspace.status_text_set(f"total time: {total_time * 1000}")

    def __del__(self):
        if self.id_texture is not None:
            del self.id_texture
