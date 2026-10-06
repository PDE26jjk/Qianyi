"""The pattern UV control the UV editor adds.

The UV editor is where a pattern's UV is seen and edited, so its sidebar is
where the one command over that layer lives: a reset, which stamps the UV back
to the pattern's own space. Nothing here resamples a pattern, rebuilds a mesh or
calls the engine - the layer is written in place, as one undo step.
"""

import numpy as np
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.pattern_mesh import seed_pattern_uv, uv_scale_value, write_vertex_uv


class QY_OT_ResetPatternUV(Operator):
    """Stamp the active pattern mesh's UV back to its own pattern space."""

    bl_idname = Operators.ResetPatternUV
    bl_label = "Reset UV"
    bl_description = ("Set this pattern's UV to its pattern-space positions "
                      "times the scene's UV scale. Vertices, sewings and the "
                      "simulation are not touched")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _active_pattern_props(context) is not None

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        if len(mesh.vertices) == 0:
            return {'CANCELLED'}
        sim_props = obj.qmyi_simulation_props
        pattern = sim_props.pattern
        # The rest positions, read the way every other consumer reads them: the
        # pattern's base shape key, falling back to the mesh for one whose keys
        # are gone. Reading the mesh directly is the same data until the two
        # drift, and then a reset would seed a different space from the one a
        # rebuild maps from.
        positions = sim_props.get_pattern_vertices()
        if positions is None:
            values = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", values)
            positions = values.reshape(-1, 3)[:, :2]
        uv = seed_pattern_uv(pattern, positions, uv_scale_value())
        write_vertex_uv(mesh, uv)
        mesh.update()
        if context.area is not None:
            context.area.tag_redraw()
        return {'FINISHED'}


def _active_pattern_props(context):
    """The simulation properties of the active object, when it is a pattern mesh."""
    obj = context.active_object
    props = getattr(obj, "qmyi_simulation_props", None)
    if obj is None or obj.type != 'MESH' or props is None or not props.is_pattern_mesh:
        return None
    return props


register, unregister = register_classes_factory((QY_OT_ResetPatternUV,))
