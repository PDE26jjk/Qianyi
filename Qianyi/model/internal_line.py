import numpy as np
from bpy.props import CollectionProperty, BoolProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .section import Section
from .geometry import Edge2D
from .model_data import ModelData, define_temp_prop, resolve_sketch, Selectable
from .. import global_data
from ..utilities.console import console


class InternalLine(PropertyGroup, ModelData, Selectable):
    edges: CollectionProperty(type=Edge2D, name="edges")
    is_loop: BoolProperty(name="is_loop", default=False)
    is_hole: BoolProperty(name="is_hole", default=False)

    def initialize(self):
        """Give this line its renderer.

        The edges answer for the Sketch the line lives in, so a point they name
        resolves without asking a pattern; the samples a mesh is built from are the
        pattern's, and are taken there.
        """
        if global_data.renderers_enabled:
            from ..gizmos.internal_line_renderer import InternalLineRenderer
            self.renderer = InternalLineRenderer(self)

    def update_render_spline_point(self):
        points = []
        for edge in self.edges:
            if len(edge.spline_points) > 0:
                points.append([p.co for p in edge.spline_points])
        if len(points) > 0:
            points = np.concatenate(points, dtype=np.float32)
        self.renderer.update_batch_spline_point(points)

    def update_render_line(self):
        render_points = []
        for i in range(len(self.edges)):
            self.edges[i].update()
            points = self.edges[i].render_points
            render_points.append(points)
        self.render_points = np.concatenate(render_points, dtype=np.float32)
        self.renderer.update_batch_edge(self.render_points)
        return self.render_points

    @property
    def sketch(self):
        """The Sketch this line is stored in, or None."""
        return resolve_sketch(self)

    def add_edge(self, start_idx, end_idx,
                 control1=None, control2=None, handle1_type="VECTOR",
                 handle2_type="VECTOR", update=True):
        # The line's own Sketch records the new edge; adding to `edges` retires
        # the wrappers this line handed out before.
        edge: Edge2D = self.edges.add()
        sketch = self.sketch
        if sketch is not None:
            sketch.own(edge)
        else:
            edge.get_temp_data()
        edge.vertex_index[0] = start_idx
        edge.vertex_index[1] = end_idx
        if control1 is not None and control2 is not None:
            edge.handle1.co = control1[:]
            edge.handle2.co = control2[:]
        edge.handle1_type = handle1_type
        edge.handle2_type = handle2_type
        if update:
            edge.update()
        return edge

define_temp_prop(InternalLine, "sketch_temp", None)
define_temp_prop(InternalLine, "sketch_uuid", -1)
define_temp_prop(InternalLine, "render_points", None)
define_temp_prop(InternalLine, "renderer", None)

register, unregister = register_classes_factory((InternalLine,))
