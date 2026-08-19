import bpy
import blf
from bpy_extras import view3d_utils

import gpu
import math
from mathutils import Vector, Matrix
from gpu_extras.batch import batch_for_shader
from typing import List, Tuple, Optional, Sequence

from .utilities.console import console_print, Console, console

# ----------------------------------------------------------------------------
# Singleton manager (module-level, like the reference global_data.temp_draw_manager)
# ----------------------------------------------------------------------------
_manager: Optional["DebugDrawManager3D"] = None


def get_manager() -> "DebugDrawManager3D":
    global _manager
    if _manager is None:
        _manager = DebugDrawManager3D()
    return _manager


def clear_manager():
    global _manager
    if _manager is not None:
        _manager.clear()


# ----------------------------------------------------------------------------
# Manager
# ----------------------------------------------------------------------------
class DebugDrawManager3D:
    """World-space debug overlay for the 3D viewport.

    All primitives are stored and (re)drawn each frame.  Batches are grouped
    by (color, width, depth) to minimize shader bind / draw call overhead.
    """

    def __init__(self):
        # Primitive storage
        self._segments: List[Tuple[Vector, Vector, Tuple[float, float, float, float], float, bool]] = []
        self._circles: List[Tuple[Vector, Vector, float, Tuple[float, float, float, float], int, float, bool]] = []
        self._arrows: List[Tuple[Vector, Vector, Tuple[float, float, float, float], float, float, float, bool]] = []
        self._capsules: List[Tuple[Vector, Vector, float, Tuple[float, float, float, float], int, float, bool]] = []
        self._points: List[Tuple[Vector, Tuple[float, float, float, float], float, bool]] = []
        self._meshes_wire: List[
            Tuple[List[Vector], List[Tuple[int, int]], Tuple[float, float, float, float], float, bool]] = []
        self._meshes_shaded: List[
            Tuple[List[Vector], List[Vector], List[Tuple[int, int, int]], Tuple[float, float, float, float], bool]] = []
        self._texts: List[Tuple[Vector, str, Tuple[float, float, float, float], int, bool]] = []

        # Light direction for shaded meshes (world space)
        self._light_dir = Vector((0.4, -0.5, 0.8)).normalized()

        # Shader cache
        self._shaders = {}

        # X-ray / global transparency support
        self._global_alpha = 1.0  # 1.0 = opaque, <1.0 = transparent
        self._xray_depth_test = True  # Keep depth test when transparent

    # ------------------------------------------------------------------ config
    def set_global_alpha(self, alpha, xray_depth_test=True):
        """Set transparency for all drawn primitives (0=fully transparent, 1=opaque)."""
        self._global_alpha = max(0.0, min(1.0, alpha))
        self._xray_depth_test = xray_depth_test
        return self

    def _apply_alpha(self, color):
        """Multiply alpha by the global transparency factor."""
        if self._global_alpha >= 1.0:
            return color
        r, g, b, a = color
        return (r, g, b, a * self._global_alpha)

    # ------------------------------------------------------------------ shaders
    def _shader(self, name: str):
        if name not in self._shaders:
            self._shaders[name] = gpu.shader.from_builtin(name)
        return self._shaders[name]

    def _get_lighting_shader(self):
        if 'lighting' not in self._shaders:
            # Blender's GPUShader auto-injects ModelViewMatrix / ProjectionMatrix / NormalMatrix.
            vert = '''
            in vec3 pos;
            in vec3 nor;
            out vec3 v_normal;
            out vec3 v_view;
            void main() {
                v_normal = normalize(NormalMatrix * nor);
                vec4 mv_pos = ModelViewMatrix * vec4(pos, 1.0);
                v_view = -mv_pos.xyz;
                gl_Position = ProjectionMatrix * mv_pos;
            }
            '''
            frag = '''
            uniform vec4 color;
            uniform vec3 light_dir;
            in vec3 v_normal;
            in vec3 v_view;
            out vec4 fragColor;
            void main() {
                vec3 N = normalize(v_normal);
                vec3 L = normalize(light_dir);
                vec3 V = normalize(v_view);
                vec3 H = normalize(L + V);
                float diff = max(dot(N, L), 0.0);
                float spec = pow(max(dot(N, H), 0.0), 32.0) * 0.25;
                float ambient = 0.25;
                vec3 c = color.rgb * (ambient + diff) + vec3(spec);
                fragColor = vec4(c, color.a);
            }
            '''
            self._shaders['lighting'] = gpu.types.GPUShader(vert, frag)
        return self._shaders['lighting']

    # ------------------------------------------------------------------ add API
    def add_line(self, p1, p2, color=(1, 0, 0, 1), width=1.0, depth=True):
        self._segments.append((Vector(p1), Vector(p2), tuple(color), float(width), bool(depth)))
        return self

    def add_dashed_line(self, p1, p2, color=(1, 0, 0, 1), width=2.0,
                        dash_length=1.0, gap_length=0., depth=True):
        """
        Draw a dashed line with clearly separated segments.
        Each dash is dash_length long, followed by a gap of gap_length.
        Both values are in world units.
        """
        start = Vector(p1)
        end = Vector(p2)
        direction = end - start
        total_length = direction.length
        if total_length < 1e-6:
            return self
        if gap_length < 1e-6:
            gap_length = dash_length
        dir_n = direction / total_length
        pos = 0.0

        while pos + dash_length <= total_length:
            seg_start = start + dir_n * pos
            seg_end = seg_start + dir_n * dash_length
            self._segments.append((seg_start, seg_end, tuple(color), float(width), bool(depth)))
            pos += dash_length + gap_length

        return self

    def add_polyline(self, points, color=(1, 1, 1, 1), closed=False, width=1.0, depth=True):
        pts = [Vector(p) for p in points]
        n = len(pts)
        if n < 2:
            return self
        for i in range(n - 1):
            self._segments.append((pts[i], pts[i + 1], tuple(color), float(width), bool(depth)))
        if closed and n > 2:
            self._segments.append((pts[-1], pts[0], tuple(color), float(width), bool(depth)))
        return self

    def add_circle(self, center, normal, radius, color=(0, 1, 0, 1), segments=48, width=1.0, depth=True):
        self._circles.append((Vector(center), Vector(normal).normalized(), float(radius),
                              tuple(color), int(segments), float(width), bool(depth)))
        return self

    def add_arrow(self, start, end, color=(1, 1, 0, 1),
                  head_length=0.2, head_angle_deg=25.0, width=1.5, depth=True):
        self._arrows.append((Vector(start), Vector(end), tuple(color),
                             float(head_length), math.radians(head_angle_deg),
                             float(width), bool(depth)))
        return self

    def add_sphere(self, center, radius, color=(0, 1, 1, 1), segments=24, width=1.0, depth=True):
        """A sphere is a capsule with zero length."""
        self._capsules.append((Vector(center), Vector(center), float(radius),
                               tuple(color), int(segments), float(width), bool(depth)))
        return self

    def add_capsule(self, p1, p2, radius, color=(0, 1, 1, 1), segments=24, width=1.0, depth=True):
        self._capsules.append((Vector(p1), Vector(p2), float(radius), tuple(color),
                               int(segments), float(width), bool(depth)))
        return self

    def add_point(self, pos, color=(1, 1, 1, 1), size=4.0, depth=True):
        self._points.append((Vector(pos), tuple(color), float(size), bool(depth)))
        return self

    def add_mesh_wireframe(self, verts, edges, color=(1, 1, 1, 1), width=1.0, depth=True):
        self._meshes_wire.append(([Vector(v) for v in verts],
                                  [(int(a), int(b)) for a, b in edges],
                                  tuple(color), float(width), bool(depth)))
        return self

    def add_mesh_shaded(self, verts, normals, faces, color=(0.7, 0.7, 0.7, 1), depth=True):
        # Fan-triangulate polygons of arbitrary size
        tris: List[Tuple[int, int, int]] = []
        for f in faces:
            if len(f) < 3:
                continue
            for i in range(1, len(f) - 1):
                tris.append((int(f[0]), int(f[i]), int(f[i + 1])))
        self._meshes_shaded.append(([Vector(v) for v in verts],
                                    [Vector(n) for n in normals],
                                    tris, tuple(color), bool(depth)))
        return self

    def add_mesh_from_object(self, obj, color=(0.7, 0.7, 0.7, 1), wireframe=False, depth=True):
        """Pull evaluated mesh data from a Blender object and queue it for drawing."""
        if obj is None or obj.type != 'MESH':
            return self
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        try:
            matrix = obj.matrix_world
            verts = [matrix @ v.co for v in mesh.vertices]
            nm = matrix.inverted_safe().transposed().to_3x3()
            normals = [(nm @ v.normal).normalized() for v in mesh.vertices]
            if wireframe:
                edges = [tuple(int(i) for i in e.vertices) for e in mesh.edges]
                self.add_mesh_wireframe(verts, edges, color, depth=depth)
            else:
                mesh.calc_loop_triangles()
                tris = [tuple(int(i) for i in lt.vertices) for lt in mesh.loop_triangles]
                self.add_mesh_shaded(verts, normals, tris, color, depth=depth)
        finally:
            eval_obj.to_mesh_clear()
        return self

    # ------------------------------------------------------------------ config
    def set_light_direction(self, direction):
        d = Vector(direction)
        if d.length > 1e-8:
            self._light_dir = d.normalized()
        return self

    def add_text(self, position, text, color=(1, 1, 1, 1), size=12, depth=True):
        """Queue a 2D text label at the given 3D world position."""
        self._texts.append((Vector(position), str(text), tuple(color), int(size), bool(depth)))
        return self

    def clear(self):
        self._segments.clear()
        self._circles.clear()
        self._arrows.clear()
        self._capsules.clear()
        self._points.clear()
        self._meshes_wire.clear()
        self._meshes_shaded.clear()
        self._texts.clear()

    # ------------------------------------------------------------------ geom
    @staticmethod
    def _circle_points(center: Vector, normal: Vector, radius: float, segments: int) -> List[Vector]:
        n = normal.normalized()
        if abs(n.z) < 0.9:
            u = n.cross(Vector((0, 0, 1)))
        else:
            u = n.cross(Vector((1, 0, 0)))
        u.normalize()
        v = n.cross(u)
        v.normalize()
        pts = []
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            pts.append(center + (u * math.cos(a) + v * math.sin(a)) * radius)
        return pts

    @staticmethod
    def _get_orthogonal_basis(axis: Vector):
        """Build an orthogonal basis (n, u, v) from a given axis."""
        n = axis.normalized()
        if abs(n.z) < 0.9:
            u = n.cross(Vector((0, 0, 1)))
        else:
            u = n.cross(Vector((1, 0, 0)))
        u.normalize()
        v = n.cross(u)
        v.normalize()
        return n, u, v

    @staticmethod
    def _capsule_segments(p1: Vector, p2: Vector, radius: float, segments: int):
        """Yield line segments for a capsule: cylinder lines, end caps (circles)
        and hemisphere outlines. Degenerates to three orthogonal circles for a sphere.
        """
        axis = p2 - p1
        length = axis.length

        # ---- sphere case ----
        if length < 1e-6:
            # Use world axes to create three orthogonal circles
            axes = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))]
            # Reduce segments per circle for performance while keeping it smooth
            seg = max(segments, 24)
            for ax in axes:
                _, u, v = DebugDrawManager3D._get_orthogonal_basis(ax)
                pts = [p1 + (math.cos(2 * math.pi * i / seg) * u +
                             math.sin(2 * math.pi * i / seg) * v) * radius
                       for i in range(seg)]
                for i in range(seg):
                    yield pts[i], pts[(i + 1) % seg]
            return

        # ---- capsule with non-zero length ----
        n, u, v = DebugDrawManager3D._get_orthogonal_basis(axis)

        # 1. cylinder lines (4 lines)
        for d in [u, -u, v, -v]:
            yield p1 + d * radius, p2 + d * radius

        # 2. end-cap circles (two circles at p1 and p2)
        seg = max(segments, 24)
        # circle at p1
        circle1 = [p1 + (math.cos(2 * math.pi * i / seg) * u +
                         math.sin(2 * math.pi * i / seg) * v) * radius
                   for i in range(seg)]
        for i in range(seg):
            yield circle1[i], circle1[(i + 1) % seg]
        # circle at p2
        circle2 = [p2 + (math.cos(2 * math.pi * i / seg) * u +
                         math.sin(2 * math.pi * i / seg) * v) * radius
                   for i in range(seg)]
        for i in range(seg):
            yield circle2[i], circle2[(i + 1) % seg]

        # 3. hemisphere outlines (cross arcs on each end)
        half_segs = max(4, segments // 2)

        # p1 hemisphere (bumps towards -n)
        for plane_vec in [u, v]:
            pts = []
            for i in range(half_segs + 1):
                a = math.pi * i / half_segs
                # From +plane_vec to -plane_vec via -n
                pts.append(p1 + (math.cos(a) * plane_vec - math.sin(a) * n) * radius)
            for i in range(len(pts) - 1):
                yield pts[i], pts[i + 1]

        # p2 hemisphere (bumps towards +n)
        for plane_vec in [u, v]:
            pts = []
            for i in range(half_segs + 1):
                a = math.pi * i / half_segs
                # From +plane_vec to -plane_vec via +n
                pts.append(p2 + (math.cos(a) * plane_vec + math.sin(a) * n) * radius)
            for i in range(len(pts) - 1):
                yield pts[i], pts[i + 1]

    @staticmethod
    def _arrow_segments(start: Vector, end: Vector, head_length: float,
                        head_angle: float) -> List[Tuple[Vector, Vector]]:
        d = end - start
        d_len = d.length
        if d_len < 1e-8:
            return []
        d /= d_len
        if head_length > d_len * 0.5:
            head_length = d_len * 0.5
        tip = end
        if abs(d.x) < 0.9:
            perp = d.cross(Vector((1, 0, 0)))
        else:
            perp = d.cross(Vector((0, 1, 0)))
        perp.normalize()
        back = -d
        s = math.sin(head_angle)
        c = math.cos(head_angle)
        left_end = tip + (back * c + perp * s) * head_length
        right_end = tip + (back * c - perp * s) * head_length
        return [(start, tip), (tip, left_end), (tip, right_end)]

    # ------------------------------------------------------------------ draw
    def _draw_segment_groups(self, segments):
        """Group segments by (color, width, depth) to reduce batch/shader churn."""
        if not segments:
            return
        groups = {}
        for p1, p2, color, width, depth in segments:
            groups.setdefault((color, width, depth), []).append((p1, p2))
        shader = self._shader('POLYLINE_UNIFORM_COLOR')
        region = bpy.context.region
        for (color, width, depth), segs in groups.items():
            coords = []
            for p1, p2 in segs:
                coords.append(tuple(p1))
                coords.append(tuple(p2))
            batch = batch_for_shader(shader, 'LINES', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", self._apply_alpha(color))
            shader.uniform_float("lineWidth", width)
            shader.uniform_float("viewportSize", (region.width, region.height))
            # Adjust depth state for transparency
            if self._global_alpha < 1.0:
                gpu.state.depth_mask_set(False)
                gpu.state.depth_test_set('LESS_EQUAL' if self._xray_depth_test else 'NONE')
            else:
                gpu.state.depth_mask_set(depth)
                gpu.state.depth_test_set('LESS_EQUAL' if depth else 'NONE')
            batch.draw(shader)

    def _draw_points(self):
        if not self._points:
            return
        shader = self._shader('UNIFORM_COLOR')
        groups = {}
        for pos, color, size, depth in self._points:
            groups.setdefault((color, size, depth), []).append(pos)
        for (color, size, depth), pts in groups.items():
            coords = [tuple(p) for p in pts]
            batch = batch_for_shader(shader, 'POINTS', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", self._apply_alpha(color))
            gpu.state.point_size_set(size)
            if self._global_alpha < 1.0:
                gpu.state.depth_mask_set(False)
                gpu.state.depth_test_set('LESS_EQUAL' if self._xray_depth_test else 'NONE')
            else:
                gpu.state.depth_mask_set(depth)
                gpu.state.depth_test_set('LESS_EQUAL' if depth else 'NONE')
            batch.draw(shader)

    def _draw_meshes_wire(self):
        if not self._meshes_wire:
            return
        shader = self._shader('POLYLINE_UNIFORM_COLOR')
        region = bpy.context.region
        for verts, edges, color, width, depth in self._meshes_wire:
            if not edges:
                continue
            flat = []
            for a, b in edges:
                flat.append(tuple(verts[a]))
                flat.append(tuple(verts[b]))
            batch = batch_for_shader(shader, 'LINES', {"pos": flat})
            shader.bind()
            shader.uniform_float("color", self._apply_alpha(color))
            shader.uniform_float("lineWidth", width)
            shader.uniform_float("viewportSize", (region.width, region.height))
            if self._global_alpha < 1.0:
                gpu.state.depth_mask_set(False)
                gpu.state.depth_test_set('LESS_EQUAL' if self._xray_depth_test else 'NONE')
            else:
                gpu.state.depth_mask_set(depth)
                gpu.state.depth_test_set('LESS_EQUAL' if depth else 'NONE')
            batch.draw(shader)

    def _draw_meshes_shaded(self):
        if not self._meshes_shaded:
            return
        shader = self._get_lighting_shader()
        prev_cull = gpu.state.cull_face_get()
        gpu.state.cull_face_set('NONE')  # double-sided for debug visualization
        for verts, normals, tris, color, depth in self._meshes_shaded:
            if not tris:
                continue
            pos = [tuple(v) for v in verts]
            nor = [tuple(n) for n in normals]
            batch = batch_for_shader(shader, 'TRIS',
                                     {"pos": pos, "nor": nor},
                                     indices=tris)
            shader.bind()
            shader.uniform_float("color", self._apply_alpha(color))
            shader.uniform_float("light_dir", tuple(self._light_dir))
            if self._global_alpha < 1.0:
                gpu.state.depth_mask_set(False)
                gpu.state.depth_test_set('LESS_EQUAL' if self._xray_depth_test else 'NONE')
            else:
                gpu.state.depth_mask_set(depth)
                gpu.state.depth_test_set('LESS_EQUAL' if depth else 'NONE')
            batch.draw(shader)
        gpu.state.cull_face_set(prev_cull)

    def _draw_texts(self, context):
        if not self._texts:
            return
        region = context.region
        rv3d = context.space_data.region_3d
        if not region or not rv3d:
            return

        font_id = 0  # built-in font

        # Enable shadow with level=5, color=black (shadow function now takes all 6 args)
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 5, 0.0, 0.0, 0.0, 1.0)
        blf.shadow_offset(font_id, 1, -1)

        for pos, text, color, size, depth in self._texts:
            coords_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, pos)
            if coords_2d is None:  # outside view or behind camera
                continue

            x, y = coords_2d
            r, g, b, a = self._apply_alpha(color)

            blf.position(font_id, x, y, 0)
            blf.size(font_id, size)
            blf.color(font_id, r, g, b, a)
            blf.draw(font_id, text)

        # Reset to sensible defaults to avoid leaking state
        blf.size(font_id, 11)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
        blf.disable(font_id, blf.SHADOW)


    def draw(self, context):
        # Automatically follow viewport X-ray mode
        space_data = context.space_data
        if space_data and space_data.type == 'VIEW_3D':
            shading = space_data.shading
            if shading.show_xray:
                # Full transparency with depth test off to mimic object X-ray
                self.set_global_alpha(0.6, xray_depth_test=False)
            else:
                self.set_global_alpha(1.0)
        else:
            self.set_global_alpha(1.0)  # fallback

        gpu.state.blend_set('ALPHA')  # Enable alpha blending for transparency

        # Tessellate higher-level primitives into line segments
        all_segments = list(self._segments)

        for center, normal, radius, color, segments, width, depth in self._circles:
            pts = self._circle_points(center, normal, radius, segments)
            n = len(pts)
            for i in range(n):
                all_segments.append((pts[i], pts[(i + 1) % n], color, width, depth))

        for start, end, color, hl, ha, width, depth in self._arrows:
            for p1, p2 in self._arrow_segments(start, end, hl, ha):
                all_segments.append((p1, p2, color, width, depth))

        for p1, p2, radius, color, segments, width, depth in self._capsules:
            for s1, s2 in self._capsule_segments(p1, p2, radius, segments):
                all_segments.append((s1, s2, color, width, depth))

        self._draw_segment_groups(all_segments)
        self._draw_points()
        self._draw_meshes_wire()
        self._draw_meshes_shaded()

        # Restore sensible defaults
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(True)
        gpu.state.blend_set('NONE')

    def draw_texts(self, context):
        self._draw_texts(context)

# ----------------------------------------------------------------------------
# Registration: mirrors the reference NodeEditor overlay registration pattern
# ----------------------------------------------------------------------------
_draw_handle_3d = None
_draw_handle_text = None


def _draw_callback_3d():
    if _manager is None:
        return
    _manager.draw(bpy.context)


def _draw_callback_text():
    if _manager is None:
        return
    _manager.draw_texts(bpy.context)


class DEBUG_OT_register_draw_3d(bpy.types.Operator):
    bl_idname = "view3d.qmyi_register_debug_draw_3d"
    bl_label = "Register 3D Debug Draw Callback"

    def execute(self, context):
        global _draw_handle_3d, _draw_handle_text
        if _draw_handle_3d is None:
            _draw_handle_3d = bpy.types.SpaceView3D.draw_handler_add(
                _draw_callback_3d, (), 'WINDOW', 'POST_VIEW'
            )
        if _draw_handle_text is None:
            _draw_handle_text = bpy.types.SpaceView3D.draw_handler_add(
                _draw_callback_text, (), 'WINDOW', 'POST_PIXEL'
            )
        # Make sure the manager singleton exists
        get_manager()
        return {'FINISHED'}



def _end():
    global _draw_handle_3d, _draw_handle_text
    if _draw_handle_3d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle_3d, 'WINDOW')
        _draw_handle_3d = None
    if _draw_handle_text is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle_text, 'WINDOW')
        _draw_handle_text = None


def _startup_cb(*args):
    # Defer registration so the GPU module is fully ready at startup
    bpy.ops.view3d.qmyi_register_debug_draw_3d()
    return None


def register():
    bpy.utils.register_class(DEBUG_OT_register_draw_3d)
    bpy.app.timers.register(_startup_cb, first_interval=1, persistent=True)


def unregister():
    _end()
    bpy.utils.unregister_class(DEBUG_OT_register_draw_3d)
    global _manager
    _manager = None


import Qianyi_DP as qydp

simulator = qydp.simulator
from .simulation.simulation_manager import simulation_manager as sm

dt2 = 0.001 ** 2


def draw_vertex_trajectory_capsules(
        vertex_data: list,
        thickness: float,
        color=(1, 0, 0, 1),
        depth=True,
        force_color=(1.0, 0.5, 0.0, 1.0),
        force_elastic_color=(0.0, 1.0, 1.0, 1.0),
):
    """
    Draw for each vertex:
      - capsule from pos_prev to pos_pred (radius = thickness)
      - arrow from pos_prev to pos_world (shows final displacement)
    """
    global dt2
    dd = get_manager()
    for v in vertex_data:
        pos_prev = Vector(v['pos_prev'])
        pos_pred = Vector(v['pos_pred'])
        pos_world = Vector(v['pos_world'])

        # Trajectory capsule: prev -> pred
        dd.add_capsule(pos_prev, pos_pred, thickness, color=color, depth=depth)

        # Displacement arrow: prev -> world
        disp = pos_world - pos_prev
        dist = disp.length
        if dist > 1e-6:
            head_len = min(0.2 * dist, 0.1)
            dd.add_arrow(pos_prev, pos_world,
                         color=color,
                         head_length=head_len,
                         head_angle_deg=25,
                         width=1.5,
                         depth=depth)
        mass = v.get('mass', None)
        if mass is not None and mass > 0.0:
            force = v.get('force', None)
            if force is not None:
                force_vec = Vector(force)
                if force_vec.length_squared > 1e-12:
                    displacement = force_vec * (dt2 / mass)
                    end_point = pos_prev + displacement
                    disp_len = displacement.length
                    if disp_len > 1e-6:
                        head_len = min(0.2 * disp_len, 0.1)
                        dd.add_arrow(pos_prev, end_point,
                                     color=force_color,
                                     head_length=head_len,
                                     head_angle_deg=25,
                                     width=1.2,
                                     depth=depth)

            force_elastic = v.get('force_elastic', None)
            if force_elastic is not None:
                fe_vec = Vector(force_elastic)
                if fe_vec.length_squared > 1e-12:
                    displacement = fe_vec * (dt2 / mass)
                    end_point = pos_prev + displacement
                    disp_len = displacement.length
                    if disp_len > 1e-6:
                        head_len = min(0.2 * disp_len, 0.1)
                        dd.add_arrow(pos_prev, end_point,
                                     color=force_elastic_color,
                                     head_length=head_len,
                                     head_angle_deg=25,
                                     width=1.2,
                                     depth=depth)


def draw_edge_trajectory_capsules(
        global_eids: list,
        thickness: float,
        color=(0, 1, 0, 1),
        depth=True
):
    dd = get_manager()
    """
    Draws an edge trajectory capsule (midpoint axis from prev to pred)
    and delegates to vertex drawing for endpoint capsules and arrows.
    """
    edge_data = [get_edge_endpoints(global_eid) for global_eid in global_eids]
    for v0, v1 in edge_data:
        A0 = Vector(v0['pos_prev'])
        A_pred = Vector(v0['pos_pred'])
        B0 = Vector(v1['pos_prev'])
        B_pred = Vector(v1['pos_pred'])

        # Edge capsule: axis = midpoints at prev and pred
        mid0 = (A0 + B0) * 0.5
        mid_pred = (A_pred + B_pred) * 0.5
        r0_sq = max((A0 - mid0).length_squared,
                    (B0 - mid0).length_squared)
        r_pred_sq = max((A_pred - mid_pred).length_squared,
                        (B_pred - mid_pred).length_squared)
        radius = math.sqrt(max(r0_sq, r_pred_sq)) + thickness

        dd.add_capsule(mid0, mid_pred, radius, color=color, depth=depth)

        # Endpoint capsules and arrows (prev->pred capsule, prev->world arrow)
        draw_vertex_trajectory_capsules([v0], thickness, color, depth)
        draw_vertex_trajectory_capsules([v1], thickness, color, depth)


def draw_triangle_trajectory_capsules(
        global_fids: list,
        thickness: float,
        color=(0, 0, 1, 1),
        depth=True
):
    """

    Draws a triangle trajectory capsule (centroid axis from prev to pred)
    and delegates to vertex drawing for the three vertices.
    """
    dd = get_manager()
    inv3 = 1.0 / 3.0
    tri_data = [get_tri_endpoints(global_fid) for global_fid in global_fids]

    for v0, v1, v2 in tri_data:
        A0 = Vector(v0['pos_prev'])
        A_pred = Vector(v0['pos_pred'])
        B0 = Vector(v1['pos_prev'])
        B_pred = Vector(v1['pos_pred'])
        C0 = Vector(v2['pos_prev'])
        C_pred = Vector(v2['pos_pred'])

        # Triangle capsule: centroid axis
        cent0 = (A0 + B0 + C0) * inv3
        cent_pred = (A_pred + B_pred + C_pred) * inv3
        r0_sq = max((A0 - cent0).length_squared,
                    (B0 - cent0).length_squared,
                    (C0 - cent0).length_squared)
        r_pred_sq = max((A_pred - cent_pred).length_squared,
                        (B_pred - cent_pred).length_squared,
                        (C_pred - cent_pred).length_squared)
        radius = math.sqrt(max(r0_sq, r_pred_sq)) + thickness

        dd.add_capsule(cent0, cent_pred, radius, color=color, depth=depth)

        # Vertex capsules and arrows
        for v in [v0, v1, v2]:
            draw_vertex_trajectory_capsules(dd, [v], thickness, color, depth)


def get_global_vertex_index(obj, local_vertex_idx):
    sim_idx = obj.qmyi_simulation_props.simulation_index
    sim_data = sm.simulated_objects[sim_idx]
    offset = sim_data['vertices_offset']
    return local_vertex_idx + offset


def get_global_edge_index(obj, local_edge_idx):
    sim_idx = obj.qmyi_simulation_props.simulation_index
    sim_data = sm.simulated_objects[sim_idx]
    offset = sim_data['edges_offset']
    return local_edge_idx + offset


def get_global_face_index(obj, local_face_idx):
    sim_idx = obj.qmyi_simulation_props.simulation_index
    sim_data = sm.simulated_objects[sim_idx]
    offset = sim_data['faces_offset']
    return local_face_idx + offset


def get_edge_endpoints(global_edge_idx):
    for sim_data in sm.simulated_objects:
        edges = sim_data['edges']
        edges_offset = sim_data['edges_offset']
        num_edges = len(edges) // 2

        if edges_offset <= global_edge_idx < edges_offset + num_edges:
            local_eid = global_edge_idx - edges_offset
            base = local_eid * 2
            local_v0 = int(edges[base])
            local_v1 = int(edges[base + 1])
            if local_v0 > local_v1:
                local_v0, local_v1 = local_v1, local_v0

            global_v0 = local_v0 + sim_data['vertices_offset']
            global_v1 = local_v1 + sim_data['vertices_offset']

            v0_data = simulator.check_point_attributes(global_v0)
            v1_data = simulator.check_point_attributes(global_v1)
            v0_data['global_vid'] = global_v0
            v1_data['global_vid'] = global_v1
            return v0_data, v1_data

    raise ValueError(f"Global edge index {global_edge_idx} not found in simulated objects.")


def get_tri_endpoints(global_tri_idx):
    for sim_data in sm.simulated_objects.values():
        triangles = sim_data['triangles']  # flat array: [v0, v1, v2, ...]
        faces_offset = sim_data['faces_offset']
        num_tris = len(triangles) // 3

        if faces_offset <= global_tri_idx < faces_offset + num_tris:
            local_tri = global_tri_idx - faces_offset
            base = local_tri * 3
            local_v0 = int(triangles[base])
            local_v1 = int(triangles[base + 1])
            local_v2 = int(triangles[base + 2])

            voff = sim_data['vertices_offset']
            gv0 = local_v0 + voff
            gv1 = local_v1 + voff
            gv2 = local_v2 + voff

            v0 = simulator.check_point_attributes(gv0)
            v1 = simulator.check_point_attributes(gv1)
            v2 = simulator.check_point_attributes(gv2)
            return v0, v1, v2

    raise ValueError(f"Global triangle index {global_tri_idx} not found in simulated objects.")


def draw_edge_collision_visualization(
        e_idx: int,  # vertex data for the second endpoint of the query edge
        invalid_color=(1, 0, 0, 1),  # red for invalid (valid=0)
        valid_color=(0.5, 0, 1, 1),  # purple for valid (valid=1)
        force_color=(1, 0.5, 0, 1),  # orange for force arrow
        dash_color=(0.8, 0.8, 0.8, 1),  # light gray for connection dashed line
        id_color=(1, 0.8, 0, 1),
        depth=True
):
    """
    Visualize edge-edge collision detection results.

    For each nearby edge:
      - draws the edge line in red (invalid) or purple (valid)
      - if valid: draws a dashed line from the hit point on the original edge
        to the hit point on the colliding edge, and a force arrow starting
        at the original hit point.
    """
    p0_data, p1_data = get_edge_endpoints(e_idx)
    collision_res = simulator.check_edge_collision_data(p0_data['global_vid'], p1_data['global_vid'])
    console_print(collision_res)
    A0 = Vector(p0_data['pos_world'])
    B0 = Vector(p1_data['pos_world'])
    mass = p0_data['mass']  # mass of the first vertex of the query edge (per request)

    nearby_edges = collision_res['nearby_edges']
    valid_flags = collision_res['valid']
    forces = collision_res['forces']
    st_list = collision_res['st']
    dd = get_manager()

    TARGET_SEGMENTS = 10
    for idx, edge_idx_signed in enumerate(nearby_edges):
        edge_idx = abs(edge_idx_signed)

        # Get colliding edge endpoints (use pos_prev for consistency)
        vA_data, vB_data = get_edge_endpoints(edge_idx)
        C0 = Vector(vA_data['pos_world'])
        D0 = Vector(vB_data['pos_world'])

        is_valid = valid_flags[idx] == 1
        color = valid_color if is_valid else invalid_color

        # Draw the nearby edge as a line
        dd.add_line(C0, D0, color=color, width=2.0, depth=depth)
        dd.add_text((C0 + D0) * 0.5, str(edge_idx_signed), color=id_color, size=20)

        if is_valid:
            s, t = st_list[idx]
            # Hit point on the original edge
            P_s = A0 + (B0 - A0) * s
            # Hit point on the colliding edge
            P_t = C0 + (D0 - C0) * t

            # Dashed connection line
            line_vec = P_t - P_s
            total_len = line_vec.length
            if total_len > 1e-6:
                # one dash segment + one gap = 2 * seg_len,
                # total_len / (2 * TARGET_SEGMENTS) gives seg_len
                seg_len = total_len / (2.0 * TARGET_SEGMENTS)
            else:
                seg_len = 0.05  # fallback for degenerate line

            dd.add_dashed_line(
                P_s, P_t,
                color=dash_color,
                width=1.5,
                dash_length=seg_len,
                gap_length=seg_len,
                depth=depth
            )

            # Force arrow (force / mass * dt2)
            force_vec = Vector(forces[idx])
            force_disp = force_vec / mass * dt2
            if force_disp.length > 1e-6:
                head_len = min(0.2 * force_disp.length, 0.05)
                dd.add_arrow(P_s, P_s + force_disp,
                             color=force_color,
                             head_length=head_len,
                             head_angle_deg=20,
                             width=1.0,
                             depth=depth)
