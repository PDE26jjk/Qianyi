"""Draw the simulation's own data over the 3D viewport.

Deliberately not built on ``debug_draw_3d.py``: that module is a scratchpad that
rebuilds one batch per primitive from Python on every redraw, which is why it is
slow. Here every pass builds at most one batch per object and per change, and
draws it with a shader of its own.

Passes, each behind its own switch in the 3D sidebar's Overlays panel:

* **vertex colours** - the simulated panels drawn again with a colour per vertex:
  the pattern editor's strain ramp, or the engine's debug values.
* **seams** - every seam drawn with its own colour, between the paired stitch
  vertices, from the panels' *current* meshes. No simulation is needed: the
  preview exists so a pattern maker can check that the connections are right,
  and it follows whatever shape the viewport is showing.
* **HUD** - what the run is doing and how fast, in the corner of the viewport.

Both drawn passes offset their vertices towards the camera in the vertex shader
(``depth_offset`` along ``camera_pos - pos``). The overlay draws the same surface
the viewport has already shaded, so without the offset the two depth values tie
and the result flickers as the view moves. The offset is a fraction of the drawn
garment's size, computed when a batch is built and pushed per draw, so orbiting
the view does not rebuild anything and the geometry is not touched.

A custom draw handler does not follow Blender's own overlay switch, so every
callback checks ``space_data.overlay.show_overlays`` first: with the overlays
hidden, all of this is hidden with them. Nothing in this module writes to the
scene, and no material is created: the material stays Blender's business.
"""

from __future__ import annotations

import blf
import bpy
import gpu
import numpy as np
from gpu.types import GPUShaderCreateInfo
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from ..declarations import Panels
from .GizmosMeshRenderer import (mesh_has_simulation_frame, mesh_strain_colors,
                                 read_vertex_colors)

HUD_MARGIN_X = 14
HUD_MARGIN_Y = 12
HUD_LINE_HEIGHT = 18
HUD_FONT_SIZE = 13

# How far towards the camera the overlay is pulled out of the surface, as a
# fraction of the drawn garment's bounding-box diagonal, with a floor for tiny
# scenes. A zero would leave the two surfaces at the same depth, which flickers.
DEPTH_OFFSET_FRACTION = 0.0015
MIN_DEPTH_OFFSET = 1e-4

_overlay = None
_draw_handle_3d = None
_draw_handle_text = None


def _manager():
    global _overlay
    if _overlay is None:
        _overlay = View3DOverlay()
    return _overlay


def _visible(context):
    """Whether this space draws Blender's overlays at all."""
    space = getattr(context, "space_data", None)
    if space is None or getattr(space, "type", None) != 'VIEW_3D':
        return False
    overlay = getattr(space, "overlay", None)
    if overlay is None:
        return False
    return bool(overlay.show_overlays)


def _camera_position(context):
    """The viewport's camera position in world space, or None."""
    region_data = getattr(context, "region_data", None)
    if region_data is None:
        return None
    return region_data.view_matrix.inverted().translation


def _pattern_objects(context):
    """Every panel mesh in the view layer, in object order."""
    objects = []
    for obj in context.view_layer.objects:
        if obj.type != 'MESH':
            continue
        if obj.qmyi_simulation_props.is_pattern_mesh:
            objects.append(obj)
    return objects


def _world_vertices(obj, depsgraph, cache):
    """An evaluated mesh's vertices in world space, read once per redraw."""
    name = obj.name
    if name in cache:
        return cache[name]
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.data
    count = len(mesh.vertices)
    if count == 0:
        cache[name] = None
        return None
    local = np.empty(count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", local)
    local = local.reshape(-1, 3)
    matrix = np.array(evaluated.matrix_world, dtype=np.float32)
    world = (matrix @ np.concatenate(
        [local, np.ones((count, 1), dtype=np.float32)], axis=1).T).T[:, :3]
    world = np.ascontiguousarray(world, dtype=np.float32)
    cache[name] = world
    return world


def _pose_signature(objects):
    """What the drawn meshes looked like: transforms and shape key values.

    Switching shape keys, dragging an object or changing a key's value all show
    up here, which is what keeps the seam preview in step with the viewport
    while nothing is being simulated.
    """
    entries = []
    for obj in objects:
        keys = obj.data.shape_keys
        if keys is None:
            shape = ()
        else:
            shape = tuple(round(float(block.value), 4)
                          for block in keys.key_blocks)
            shape = shape + (int(obj.active_shape_key_index),)
        matrix = np.array(obj.matrix_world, dtype=np.float32)
        entries.append((obj.name, shape,
                        tuple(np.round(matrix.ravel(), 4).tolist())))
    return tuple(entries)


def _color_key(color):
    """A sewing's colour, rounded so equal colours group into one batch."""
    return tuple(round(float(value), 4) for value in color[:3])


class View3DOverlay:
    """The overlay's shader and its cached batches."""

    def __init__(self):
        self.shader = None
        self.surface_batches = []
        self.surface_key = None
        self.seam_batch = None
        self.seam_key = None
        self.seam_count = 0
        self.depth_offset = MIN_DEPTH_OFFSET

    # ------------------------------------------------------------------ shader
    def ensure_shader(self):
        if self.shader is not None:
            return True
        shader_info = GPUShaderCreateInfo()
        shader_info.vertex_in(0, 'VEC3', "pos")
        shader_info.vertex_in(1, 'VEC4', "color")
        interface = gpu.types.GPUStageInterfaceInfo("qianyi_view3d_overlay")
        interface.smooth('VEC4', "vColor")
        shader_info.vertex_out(interface)
        shader_info.fragment_out(0, 'VEC4', "fragColor")
        shader_info.push_constant('MAT4', "ModelMatrix")
        shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
        # The camera position and the lift travel together in one vector: a
        # single VEC4 push constant is the form every other shader in this
        # add-on uses, and it keeps the two values in step by construction.
        shader_info.push_constant('VEC4', "camera_and_offset")
        # Positions arrive in world space (ModelMatrix is the identity), so the
        # only transform left is the viewport's own view/projection. Pulling the
        # vertex towards the camera by depth_offset is what keeps this pass from
        # tying with the surface Blender has already shaded.
        shader_info.vertex_source("""
        void main()
        {
            vec3 camera_pos = camera_and_offset.xyz;
            float depth_offset = camera_and_offset.w;
            vec3 to_camera = camera_pos - pos;
            float distance = length(to_camera);
            vec3 lifted = pos + (distance > 0.0
                                 ? (to_camera / distance) * depth_offset
                                 : vec3(0.0));
            gl_Position = ModelViewProjectionMatrix * ModelMatrix * vec4(lifted, 1.0);
            vColor = color;
        }
        """)
        shader_info.fragment_source("""
        void main()
        {
            fragColor = vColor;
        }
        """)
        self.shader = gpu.shader.create_from_info(shader_info)
        return True

    def _bind_uniforms(self, context, offset=None):
        """Bind the shader and push the view-dependent values."""
        camera = _camera_position(context)
        position = tuple(camera) if camera else (0.0, 0.0, 0.0)
        lift = float(self.depth_offset if offset is None else offset)
        self.shader.bind()
        self.shader.uniform_float("ModelMatrix", Matrix.Identity(4))
        self.shader.uniform_float("camera_and_offset",
                                  (position[0], position[1], position[2], lift))

    # ----------------------------------------------------------------- surface
    def _build_surface(self, context, objects, mode):
        """One triangle batch per panel, coloured by the requested mode."""
        depsgraph = context.evaluated_depsgraph_get()
        cache = {}
        batches = []
        span = 0.0
        for obj in objects:
            colors = (mesh_strain_colors(obj) if mode == 'STRESS'
                      else read_vertex_colors(obj.data))
            if colors is None:
                continue
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.data
            count = len(mesh.vertices)
            if count == 0 or len(colors) != count:
                continue
            world = _world_vertices(obj, depsgraph, cache)
            if world is None:
                continue
            extent = world.max(axis=0) - world.min(axis=0)
            span = max(span, float(np.linalg.norm(extent)))
            mesh.calc_loop_triangles()
            triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
            mesh.loop_triangles.foreach_get("vertices", triangles)
            if triangles.size == 0:
                continue
            batches.append(batch_for_shader(
                self.shader, 'TRIS',
                {"pos": world,
                 "color": np.ascontiguousarray(colors, dtype=np.float32)},
                indices=triangles.reshape(-1, 3)))
        self.depth_offset = max(MIN_DEPTH_OFFSET, DEPTH_OFFSET_FRACTION * span)
        return batches

    def draw_surface(self, context, mode):
        from ..simulation.simulation_manager import simulation_manager

        objects = [obj for obj in _pattern_objects(context)
                   if mesh_has_simulation_frame(obj)]
        if not objects:
            return
        key = (mode, simulation_manager.frame_key(),
               tuple(obj.name for obj in objects))
        if key != self.surface_key:
            self.surface_batches = self._build_surface(context, objects, mode)
            self.surface_key = key
        if not self.surface_batches:
            return

        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        self._bind_uniforms(context)
        for batch in self.surface_batches:
            batch.draw(self.shader)

    # ------------------------------------------------------------------- seams
    def _seam_segments(self, context):
        """The seam preview, as positions in the panel's *current* shape.

        Every seam contributes one line per paired stitch vertex, in the seam's
        own colour, taken from the scene's sewing objects and the evaluated
        panel meshes - no simulation state is involved, so the preview is there
        whether or not anything has been simulated and whatever shape key the
        panels are showing.
        """
        depsgraph = context.evaluated_depsgraph_get()
        cache = {}
        chunks = []
        colors = []
        span = 0.0
        for project in bpy.data.node_groups:
            if project.bl_idname != Panels.QianyiNodeTree:
                continue
            for sewing in project.sewings:
                try:
                    data = sewing.get_stitch_data()
                    first = sewing.pattern1.mesh_object if sewing.pattern1 else None
                    second = sewing.pattern2.mesh_object if sewing.pattern2 else None
                except Exception:
                    # A seam whose sides cannot be resolved has nothing to draw.
                    continue
                if first is None or second is None:
                    continue
                world_a = _world_vertices(first, depsgraph, cache)
                world_b = _world_vertices(second, depsgraph, cache)
                if world_a is None or world_b is None:
                    continue
                stitches = np.asarray(data["stitches"], dtype=np.int64)
                if stitches.size == 0:
                    continue
                if (stitches[:, 0].max() >= len(world_a)
                        or stitches[:, 1].max() >= len(world_b)):
                    continue
                # One line per pair: a0, b0, a1, b1, ...
                points = np.stack((world_a[stitches[:, 0]],
                                   world_b[stitches[:, 1]]),
                                  axis=1).reshape(-1, 3)
                chunks.append(points)
                colors.append(np.tile(
                    np.array((*_color_key(sewing.color), 1.0), dtype=np.float32),
                    (len(points), 1)))
                extent = points.max(axis=0) - points.min(axis=0)
                span = max(span, float(np.linalg.norm(extent)))
        if not chunks:
            return None
        return (np.concatenate(chunks).astype(np.float32),
                np.concatenate(colors).astype(np.float32), span)

    def draw_seams(self, context, qmyi):
        from ..simulation.simulation_manager import simulation_manager

        objects = [obj for obj in _pattern_objects(context)]
        # The preview follows the viewport: the pose signature covers shape key
        # switches and object moves, and the engine's frame counter is only an
        # extra "the simulation advanced" term - the seam data itself comes from
        # the scene, so this works with no simulation at all.
        key = (simulation_manager.frame_key(), int(bpy.context.scene.frame_current),
               _pose_signature(objects), float(qmyi.view3d_seam_width))
        if key != self.seam_key:
            built = self._seam_segments(context)
            if built is None:
                self.seam_batch = None
                self.seam_count = 0
            else:
                positions, colors, span = built
                # The seam lines sit on the cloth, so they need the same lift
                # towards the camera as the colouring does.
                self.depth_offset = max(MIN_DEPTH_OFFSET,
                                        DEPTH_OFFSET_FRACTION * span)
                self.seam_batch = batch_for_shader(
                    self.shader, 'LINES', {"pos": positions, "color": colors})
                self.seam_count = len(positions) // 2
            self.seam_key = key
        if self.seam_batch is None:
            return

        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.line_width_set(float(qmyi.view3d_seam_width))
        self._bind_uniforms(context)
        self.seam_batch.draw(self.shader)
        gpu.state.line_width_set(1.0)


def draw_view3d():
    """POST_VIEW: the vertex colouring and the seams."""
    context = bpy.context
    scene = getattr(context, "scene", None)
    qmyi = getattr(scene, "qmyi", None)
    if qmyi is None or not _visible(context):
        return
    mode = qmyi.view3d_vertex_colors
    if mode == 'OFF' and not qmyi.view3d_seams:
        return
    overlay = _manager()
    if not overlay.ensure_shader():
        return
    if mode != 'OFF':
        overlay.draw_surface(context, mode)
    if qmyi.view3d_seams:
        overlay.draw_seams(context, qmyi)


def draw_hud():
    """POST_PIXEL: what the run is doing and how fast, in the corner."""
    context = bpy.context
    scene = getattr(context, "scene", None)
    qmyi = getattr(scene, "qmyi", None)
    if qmyi is None or not qmyi.view3d_hud or not _visible(context):
        return
    if getattr(context, "region", None) is None:
        return

    from ..simulation.simulation_manager import simulation_manager

    summary = simulation_manager.rts_summary()
    if summary is None:
        return
    lines = []
    if summary["running"]:
        lines.append("Simulating")
    lines.append("RTS: {rts:.2f} = {sim:.2f}ms / {wall:.1f}ms".format(
        rts=summary["rts"], sim=summary["sim_ms"], wall=summary["wall_ms"]))
    solver = getattr(getattr(qmyi, "solver", None), "solver_name", "")
    lines.append(f"{solver} · frame {simulation_manager.run_count}")

    font = 0
    blf.size(font, HUD_FONT_SIZE)
    y = HUD_MARGIN_Y
    for line in lines:
        blf.position(font, HUD_MARGIN_X, y, 0)
        blf.color(font, 1.0, 1.0, 1.0, 0.9)
        blf.draw(font, line)
        y += HUD_LINE_HEIGHT


def register():
    global _draw_handle_3d, _draw_handle_text
    if bpy.app.background:
        # A background session has no viewport, and Blender refuses to create
        # GPU shaders in it.
        return
    if _draw_handle_3d is None:
        _draw_handle_3d = bpy.types.SpaceView3D.draw_handler_add(
            draw_view3d, (), 'WINDOW', 'POST_VIEW')
    if _draw_handle_text is None:
        _draw_handle_text = bpy.types.SpaceView3D.draw_handler_add(
            draw_hud, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _draw_handle_3d, _draw_handle_text, _overlay
    if _draw_handle_3d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle_3d, 'WINDOW')
        _draw_handle_3d = None
    if _draw_handle_text is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle_text, 'WINDOW')
        _draw_handle_text = None
    _overlay = None
