import math

import bpy
import gpu
import mathutils
import numpy as np
from gpu.types import GPUShader, GPUShaderCreateInfo
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from .. import global_data
from ..utilities.coords_transform import create_2d_matrix
from ..utilities.strain import strain_colors, vertex_strain


def read_vertex_colors(mesh):
    """The mesh's ``Color`` attribute as an (N, 4) float32 array, or None.

    The simulation bridge writes the engine's per-vertex debug colours into
    this attribute, so a panel mesh that has been stepped carries one entry per
    vertex. Anything else - no attribute, or a vertex count that no longer
    matches the mesh - reads as "no data".
    """
    attributes = getattr(mesh, "color_attributes", None)
    if attributes is None or "Color" not in attributes:
        return None
    attribute = attributes["Color"]
    count = len(mesh.vertices)
    if count == 0 or len(attribute.data) != count:
        return None
    values = np.empty(count * 4, dtype=np.float32)
    attribute.data.foreach_get("color", values)
    return values.reshape(-1, 4)


def mesh_has_simulation_frame(obj):
    """Whether the engine has produced a frame for this mesh.

    A fresh mesh also has a ``Color`` attribute - and a fresh ``QYSim`` shape key
    holding the rest shape - so the flag the simulation manager raises when it
    applies a frame is what decides, not the presence of either.
    """
    if obj is None or obj.type != 'MESH':
        return False
    from ..simulation.simulation_manager import simulation_manager
    return simulation_manager.has_simulation_frame(obj)


def read_shape_key_vertices(mesh, name):
    """One shape key's points as an (N, 3) float32 array, or None.

    The bridge stores the flat pattern in ``QYBasis`` and the engine's last
    frame in ``QYSim``, both in the same local space, which is what makes the
    two comparable for a strain readout.
    """
    keys = mesh.shape_keys.key_blocks if mesh.shape_keys is not None else None
    if keys is None or name not in keys:
        return None
    count = len(mesh.vertices)
    if count == 0:
        return None
    values = np.empty(count * 3, dtype=np.float32)
    keys[name].data.foreach_get("co", values)
    return values.reshape(-1, 3)


def mesh_strain_colors(obj):
    """Per-vertex strain of a simulated panel, as (N, 4) float32 colours.

    Returns None when the mesh has no rest or no simulated vertex set to compare.
    See ``utilities/strain.py`` for what the value is and what the ramp means.
    """
    if obj is None or obj.type != 'MESH':
        return None
    mesh = obj.data
    rest = read_shape_key_vertices(mesh, "QYBasis")
    sim = read_shape_key_vertices(mesh, "QYSim")
    if rest is None or sim is None or rest.shape != sim.shape:
        return None
    edges = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edges)
    strain = vertex_strain(rest, sim, edges.reshape(-1, 2))
    return strain_colors(strain)


class MeshRenderer:
    shader = None
    color_shader = None

    def __init__(self, pattern):
        self.pattern_uuid = pattern.global_uuid
        if self.shader is None:
            # self.shader = GPUShader(vertex_shader, fragment_shader)
            self.shader = self._create_shader()
        if self.color_shader is None:
            self.color_shader = self._create_color_shader()
        self.batch_line = None
        self.batch_triangle = None
        self.batch_color_triangle = None
        self._color_values = None
        # What the current colour batch was built from: (display mode, engine
        # frame). Rebuilding is skipped while both are unchanged, so a redraw
        # does not re-derive the colours or re-upload the batch.
        self._color_key = None
        self.obj = None

    def _create_shader(self):
        shader_info = GPUShaderCreateInfo()

        shader_info.vertex_in(0, 'VEC3', "pos")
        shader_info.fragment_out(0, 'VEC4', "fragColor")

        shader_info.push_constant('MAT4', "ModelMatrix")
        shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
        shader_info.push_constant('VEC4', "color")

        shader_info.vertex_source("""
        void main()
        {
            gl_Position = ModelViewProjectionMatrix * ModelMatrix * vec4(pos.x,pos.y,0., 1.0);
        }
        """)
        shader_info.fragment_source("""
        void main()
        {
            fragColor = color;
        }
        """)

        return gpu.shader.create_from_info(shader_info)

    def _create_color_shader(self):
        """The same fill, but taking the colour per vertex from the mesh.

        Used by the stress and debug display modes: the bridge writes the
        engine's per-vertex values into the ``Color`` attribute and this shader
        paints them over the flat panel.
        """
        shader_info = GPUShaderCreateInfo()

        shader_info.vertex_in(0, 'VEC3', "pos")
        shader_info.vertex_in(1, 'VEC4', "color")
        interface = gpu.types.GPUStageInterfaceInfo("qianyi_mesh_color")
        interface.smooth('VEC4', "vColor")
        shader_info.vertex_out(interface)
        shader_info.fragment_out(0, 'VEC4', "fragColor")

        shader_info.push_constant('MAT4', "ModelMatrix")
        shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")

        shader_info.vertex_source("""
        void main()
        {
            gl_Position = ModelViewProjectionMatrix * ModelMatrix * vec4(pos.x, pos.y, 0., 1.0);
            vColor = color;
        }
        """)
        shader_info.fragment_source("""
        void main()
        {
            fragColor = vColor;
        }
        """)

        return gpu.shader.create_from_info(shader_info)

    @property
    def pattern(self):
        return global_data.get_obj_by_uuid(self.pattern_uuid, False)

    def create_batch(self, obj):
        """创建网格批次（只调用一次）"""
        if not obj or obj.type != 'MESH':
            return None

        mesh = obj.data

        # 确保 loop_triangles 数据是最新的 (通常很快)
        mesh.calc_loop_triangles()

        # --- 1. 获取顶点坐标 (Nx3) ---
        # 创建一个空的 numpy 数组，形状为 (顶点数, 3)
        vertices = np.empty((len(mesh.vertices), 3), dtype=np.float32)
        # 使用 foreach_get 直接将 C 内存数据复制到 numpy 数组中
        # .ravel() 将 2D 数组展平为 1D，因为 foreach_get 需要平铺的数据
        mesh.vertices.foreach_get("co", vertices.ravel())
        vertices *= 1000.
        # --- 2. 获取边索引 (Nx2) ---
        edges = np.empty((len(mesh.edges), 2), dtype=np.int32)
        mesh.edges.foreach_get("vertices", edges.ravel())

        # --- 3. 获取三角形索引 (Nx3) ---
        triangles = np.empty((len(mesh.loop_triangles), 3), dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles.ravel())

        if self.shader is None:
            self.setup_shader()

        # --- 4. 创建批次 ---
        # batch_for_shader 完美支持 numpy 数组作为输入，无需转回 Python List
        self.batch_line = batch_for_shader(
            self.shader, 'LINES',
            {"pos": vertices},  # numpy 数组直接传入
            indices=edges  # numpy 数组直接传入
        )

        self.batch_triangle = batch_for_shader(
            self.shader, 'TRIS',
            {"pos": vertices},  # 复用同一个顶点数据
            indices=triangles
        )

        return self.batch_line, self.batch_triangle

    def color_source(self, mode):
        """The (N, 4) colours a display mode paints this panel with, or None.

        ``DEBUG`` is the engine's own per-vertex buffer (the collision debug
        marks). ``STRESS`` is strain derived from the rest and simulated vertex
        sets, because the engine does not report a per-vertex stress yet.
        """
        if not mesh_has_simulation_frame(self.obj):
            return None
        cache_key = (mode, self._frame_key())
        if cache_key == self._color_key and self._color_values is not None:
            return self._color_values, cache_key
        if mode == 'DEBUG':
            colors = read_vertex_colors(self.obj.data)
        elif mode == 'STRESS':
            colors = mesh_strain_colors(self.obj)
        else:
            colors = None
        return colors, cache_key

    def _frame_key(self):
        """A value that changes whenever the engine applies a frame."""
        from ..simulation.simulation_manager import simulation_manager
        return simulation_manager.frame_key()

    def create_color_batch(self, obj, colors):
        """The triangle batch with the given per-vertex colours attached.

        Returns None when the mesh has no readable colours, so the caller can
        fall back to the solid fill. The vertex positions are the mesh's own
        (the flat panel), which is what the pattern window shows.
        """
        if not obj or obj.type != 'MESH' or colors is None:
            return None
        mesh = obj.data
        if len(colors) != len(mesh.vertices):
            return None

        mesh.calc_loop_triangles()

        vertices = np.empty((len(mesh.vertices), 3), dtype=np.float32)
        mesh.vertices.foreach_get("co", vertices.ravel())
        vertices *= 1000.

        triangles = np.empty((len(mesh.loop_triangles), 3), dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles.ravel())

        self.batch_color_triangle = batch_for_shader(
            self.color_shader, 'TRIS',
            {"pos": vertices, "color": colors},
            indices=triangles,
        )
        return self.batch_color_triangle

    def draw_fill_mesh_vertex_colors(self, mode):
        """Fill the panel mesh with one display mode's per-vertex colours.

        Returns False when that mode has no data for this mesh yet, so the
        caller falls back to the solid fabric fill and the header can say why.
        """
        source = self.color_source(mode)
        if source is None:
            return False
        colors, cache_key = source
        if colors is None:
            return False
        if self.batch_color_triangle is None or self._color_key != cache_key:
            if self.create_color_batch(self.obj, colors) is None:
                return False
            self._color_values = colors
            self._color_key = cache_key

        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')

        self.color_shader.bind()
        self.color_shader.uniform_float("ModelMatrix", self.get_world_matrix())
        self.batch_color_triangle.draw(self.color_shader)
        return True

    def get_world_matrix(self):
        return self.pattern.calc_matrix()

    def draw_fill_mesh(self, color=(1.0, 1.0, 1.0, 0.5), draw_id=False):
        if not self.obj or not self.batch_triangle or not self.shader or not self.pattern:
            return
        # 设置GPU状态
        if draw_id:
            gpu.state.blend_set('NONE')
        else:
            gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')

        self.shader.bind()

        self.shader.uniform_float("ModelMatrix", self.get_world_matrix())
        self.shader.uniform_float("color", color)
        self.batch_triangle.draw(self.shader)

    def draw_mesh_lines(self, selected=False):
        if not self.obj or not self.batch_line or not self.shader or not self.pattern:
            return

        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')

        self.shader.bind()

        transform_matrix = self.pattern.calc_matrix()
        self.shader.uniform_float("ModelMatrix", transform_matrix)
        if selected:
            self.shader.uniform_float("color", (0.843, 0.596, 0.153, 1.0))
        else:
            self.shader.uniform_float("color", (1.0, 1.0, 1.0, 0.5))
        # 绘制批次
        gpu.state.line_width_set(1.0)
        self.batch_line.draw(self.shader)

    def start_rendering(self, obj):
        """开始渲染指定对象"""
        self.obj = None
        if not obj:
            return False

        self.batch_line, self.batch_triangle = self.create_batch(obj)

        if not self.batch_triangle:
            return False

        self.obj = obj
        return True
