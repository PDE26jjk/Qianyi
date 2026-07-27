import bpy
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

        # Light direction for shaded meshes (world space)
        self._light_dir = Vector((0.4, -0.5, 0.8)).normalized()

        # Shader cache
        self._shaders = {}

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

    def clear(self):
        self._segments.clear()
        self._circles.clear()
        self._arrows.clear()
        self._capsules.clear()
        self._points.clear()
        self._meshes_wire.clear()
        self._meshes_shaded.clear()

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
            shader.uniform_float("color", color)
            shader.uniform_float("lineWidth", width)
            shader.uniform_float("viewportSize", (region.width, region.height))
            gpu.state.depth_test_set('LESS_EQUAL' if depth else 'NONE')
            gpu.state.depth_mask_set(depth)
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
            shader.uniform_float("color", color)
            gpu.state.point_size_set(size)
            gpu.state.depth_test_set('LESS_EQUAL' if depth else 'NONE')
            gpu.state.depth_mask_set(depth)
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
            shader.uniform_float("color", color)
            shader.uniform_float("lineWidth", width)
            shader.uniform_float("viewportSize", (region.width, region.height))
            gpu.state.depth_test_set('LESS_EQUAL' if depth else 'NONE')
            gpu.state.depth_mask_set(depth)
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
            shader.uniform_float("color", color)
            shader.uniform_float("light_dir", tuple(self._light_dir))
            gpu.state.depth_test_set('LESS_EQUAL' if depth else 'NONE')
            gpu.state.depth_mask_set(depth)
            batch.draw(shader)
        gpu.state.cull_face_set(prev_cull)

    def draw(self, context):
        space_data = context.space_data
        if space_data and space_data.type == 'VIEW_3D':
            shading = space_data.shading
            console.warning("show_xray", shading.show_xray )
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


# ----------------------------------------------------------------------------
# Registration: mirrors the reference NodeEditor overlay registration pattern
# ----------------------------------------------------------------------------
_draw_handle = None


def _draw_callback():
    if _manager is None:
        return
    _manager.draw(bpy.context)


class DEBUG_OT_register_draw_3d(bpy.types.Operator):
    bl_idname = "view3d.qmyi_register_debug_draw_3d"
    bl_label = "Register 3D Debug Draw Callback"

    def execute(self, context):
        global _draw_handle
        if _draw_handle is None:
            _draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                _draw_callback, (), 'WINDOW', 'POST_VIEW'
            )
        # Make sure the manager singleton exists
        get_manager()
        return {'FINISHED'}


def _end():
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None


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
