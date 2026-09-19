"""Draw the project's silhouette objects behind the panels.

The pattern window is a 2D space in millimetres, and every panel is drawn
through its own anchor and rotation. The silhouette is drawn in the same space:
the chosen collection's meshes are taken in world space, projected along one
world axis into a plane, scaled from metres to millimetres and offset by the
project's own view offset. A one metre body edge therefore lands on 1000 mm of
pattern space, which is what makes the guide usable for alignment by eye. The
projected triangles are drawn filled and, optionally, with their mesh edges, so
a panel can be aligned against the body's surface and its seams.

Nothing here touches the scene: the guide reads evaluated meshes and draws, and
the projection never enters a panel, a mesh or the engine payload.

Cost: the projection and the two batches are rebuilt only when the object set,
their transforms, the settings or the engine's frame change. A settled avatar
therefore costs one signature comparison per redraw; a deforming one is
followed at most every ``MIN_REBUILD_INTERVAL`` seconds, because rebuilding two
batches of a dense body on every redraw would dominate the window.
"""

from __future__ import annotations

import time

import bpy
import gpu
import numpy as np
from gpu.types import GPUShaderCreateInfo
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix


# Two world axes are kept per projection axis, in the order the pattern window
# uses them: the first is the window's x, the second its y.
AXIS_PLANES = {
    'X': (1, 2),
    'Y': (0, 2),
    'Z': (0, 1),
}

# A deforming avatar is followed at most this often.
MIN_REBUILD_INTERVAL = 0.05


def _projection_axes(axis):
    """The two world components kept when projecting along ``axis``."""
    return AXIS_PLANES.get(axis, AXIS_PLANES['Y'])


class SilhouetteGuide:
    """Projects the project's silhouette collection into the pattern window."""

    def __init__(self):
        self.shader = None
        self.batch_fill = None
        self.batch_mesh = None
        self.signature = None
        self.last_build = 0.0

    # ------------------------------------------------------------------ shader
    def _ensure_shader(self):
        if self.shader is not None:
            return True
        shader_info = GPUShaderCreateInfo()
        shader_info.vertex_in(0, 'VEC2', "pos")
        shader_info.fragment_out(0, 'VEC4', "fragColor")
        shader_info.push_constant('MAT4', "ModelMatrix")
        shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
        shader_info.push_constant('VEC4', "color")
        shader_info.vertex_source("""
        void main()
        {
            gl_Position = ModelViewProjectionMatrix * ModelMatrix * vec4(pos, 0.0, 1.0);
        }
        """)
        shader_info.fragment_source("""
        void main()
        {
            fragColor = color;
        }
        """)
        self.shader = gpu.shader.create_from_info(shader_info)
        return True

    # ------------------------------------------------------------- projection
    def objects(self, project):
        """The mesh objects the project asks to project, in collection order."""
        collection = getattr(project, "silhouette_collection", None)
        if collection is None:
            return []
        return [obj for obj in collection.all_objects if obj.type == 'MESH']

    def signature_of(self, project, objects):
        """What the cached projection was built from.

        The last entry is the engine's frame key, which advances whenever the
        simulation applies a frame - that is what makes a deforming avatar
        follow without hashing its vertices on every redraw.
        """
        from ..simulation.simulation_manager import simulation_manager

        entries = []
        for obj in objects:
            matrix = np.array(obj.matrix_world, dtype=np.float32)
            entries.append((obj.name, len(obj.data.vertices),
                            tuple(np.round(matrix.ravel(), 3).tolist())))
        return (tuple(entries),
                project.silhouette_axis,
                round(float(project.silhouette_offset[0]), 3),
                round(float(project.silhouette_offset[1]), 3),
                bool(project.silhouette_show_mesh),
                simulation_manager.frame_key())

    def _project(self, objects, depsgraph, axis, offset):
        """``(fill_batch_arrays, mesh_batch_arrays)`` for the given objects.

        Returns None when nothing could be projected. Vertices are concatenated
        and the triangles and edges are re-indexed, so one batch carries the
        whole collection.
        """
        keep = _projection_axes(axis)
        positions = []
        triangles = []
        edges = []
        vertex_offset = 0
        for obj in objects:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.data
            count = len(mesh.vertices)
            if count == 0:
                continue

            local = np.empty(count * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", local)
            local = local.reshape(-1, 3)
            homogeneous = np.concatenate(
                [local, np.ones((count, 1), dtype=np.float32)], axis=1)
            world = (np.array(evaluated.matrix_world, dtype=np.float32)
                     @ homogeneous.T).T[:, :3]
            points = np.column_stack((world[:, keep[0]], world[:, keep[1]]))
            # Metres to millimetres: the pattern space is 1:1 with the body.
            points = points * 1000.0 + offset
            positions.append(points.astype(np.float32))

            mesh.calc_loop_triangles()
            mesh_triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
            mesh.loop_triangles.foreach_get("vertices", mesh_triangles)
            if mesh_triangles.size:
                triangles.append(mesh_triangles.reshape(-1, 3) + vertex_offset)

            mesh_edges = np.empty(len(mesh.edges) * 2, dtype=np.int32)
            mesh.edges.foreach_get("vertices", mesh_edges)
            if mesh_edges.size:
                edges.append(mesh_edges.reshape(-1, 2) + vertex_offset)

            vertex_offset += count

        if not positions or vertex_offset == 0:
            return None
        return (np.concatenate(positions), triangles, edges)

    def build(self, project, depsgraph):
        """Rebuild the cached batches when something they depend on changed."""
        objects = self.objects(project)
        if not objects:
            self.batch_fill = None
            self.batch_mesh = None
            self.signature = None
            return False

        signature = self.signature_of(project, objects)
        if signature == self.signature:
            return self.batch_fill is not None or self.batch_mesh is not None

        now = time.monotonic()
        only_frame_changed = (self.signature is not None
                              and self.signature[:-1] == signature[:-1])
        if only_frame_changed and (now - self.last_build) < MIN_REBUILD_INTERVAL:
            # Keep the previous projection until the interval has passed; the
            # signature is deliberately not stored, so the next redraw retries.
            return self.batch_fill is not None or self.batch_mesh is not None

        offset = np.array((float(project.silhouette_offset[0]),
                           float(project.silhouette_offset[1])), dtype=np.float32)
        projected = self._project(objects, depsgraph, project.silhouette_axis, offset)
        self.signature = signature
        self.last_build = now
        if projected is None:
            self.batch_fill = None
            self.batch_mesh = None
            return False

        self._ensure_shader()
        positions, triangles, edges = projected
        triangle_indices = (np.concatenate(triangles) if triangles
                            else np.zeros((0, 3), dtype=np.int32))
        edge_indices = np.concatenate(edges) if edges else np.zeros((0, 2), dtype=np.int32)
        self.batch_fill = batch_for_shader(
            self.shader, 'TRIS', {"pos": positions}, indices=triangle_indices)
        self.batch_mesh = (batch_for_shader(
            self.shader, 'LINES', {"pos": positions}, indices=edge_indices)
            if project.silhouette_show_mesh and edge_indices.size else None)
        return True

    # ------------------------------------------------------------------ draw
    def draw(self, context, project):
        """Draw the guide behind the panels; does nothing when it is off."""
        if project is None or not getattr(project, "show_silhouette", False):
            return
        if not self._ensure_shader():
            return
        depsgraph = context.evaluated_depsgraph_get()
        if not self.build(project, depsgraph):
            return

        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        gpu.state.line_width_set(1.0)
        self.shader.bind()
        self.shader.uniform_float("ModelMatrix", Matrix.Identity(4))

        color = tuple(project.silhouette_color)
        if self.batch_fill is not None and len(color) >= 3:
            self.shader.uniform_float(
                "color", (color[0], color[1], color[2],
                          float(project.silhouette_opacity)))
            self.batch_fill.draw(self.shader)
        if self.batch_mesh is not None and len(color) >= 3:
            self.shader.uniform_float(
                "color", (color[0], color[1], color[2],
                          float(project.silhouette_mesh_opacity)))
            self.batch_mesh.draw(self.shader)
