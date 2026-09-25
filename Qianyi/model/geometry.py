import math
import re

import numpy as np
from bpy.props import FloatVectorProperty, CollectionProperty, EnumProperty, IntVectorProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .model_data import ModelData, define_temp_prop, resolve_sketch, Selectable
from .section import Section
from .. import global_data
from ..utilities.console import console
from ..utilities.geometric_operation import resample_polyline, generate_curve_points


class Vertex2D(PropertyGroup, ModelData, Selectable):
    """Vertex"""
    co: FloatVectorProperty(
        name="coordinates",
        description="The coordinates of the point",
        subtype="XYZ",
        size=2,
        unit="LENGTH",
        # update=tag_update,
    )

    @property
    def position(self):
        return np.asarray(self.co)

    @position.setter
    def position(self, value):
        self.co[0] = value[0]
        self.co[1] = value[1]

    def clear_temp_data(self):
        self.sketch_temp = None
        self.sketch_uuid = -1

    @property
    def sketch(self):
        """The Sketch this point is stored in, or None."""
        return resolve_sketch(self)


define_temp_prop(Vertex2D, "sketch_temp", None)
define_temp_prop(Vertex2D, "sketch_uuid", -1)
define_temp_prop(Vertex2D, "impacted", False)
define_temp_prop(Vertex2D, "proxy", None)

# EdgeType = [
#     ("BESSEL", "Bessel", "", 1),
#     ("CUBIC_SPLINE", "points", "", 2),  # cubic spline
# ]

HandleType = [
    ("ALIGNED", "Aligned", "Aligned handles", 0, 1),
    ("VECTOR", "Vector", "Vector handles", 0, 2),
    ("FREE", "Free", "Free handles", 0, 4),
]


class Edge2D(PropertyGroup, ModelData, Selectable):
    # type: EnumProperty(name="edgeType", items=EdgeType, default="BESSEL")
    vertex_index: IntVectorProperty(name="vertexIndex", size=2, default=(0, 0))
    handles: CollectionProperty(name="handles", type=Vertex2D, )
    handle1_type: EnumProperty(name="handle1Type", items=HandleType, default="VECTOR")
    handle2_type: EnumProperty(name="handle2Type", items=HandleType, default="VECTOR")
    spline_points: CollectionProperty(name="splinePoints", type=Vertex2D, )
    bbox: FloatVectorProperty(name="bBox", size=4, default=(0, 0, 1, 1))

    @property
    def sketch(self):
        """The Sketch this edge is stored in, or None."""
        return resolve_sketch(self)

    def reverse(self):
        self.vertex_index[0], self.vertex_index[1] = self.vertex_index[1], self.vertex_index[0]
        self.handle1.co[:], self.handle2.co[:] = self.handle2.co[:], self.handle1.co[:]
        self.handle1_type, self.handle2_type = self.handle2_type, self.handle1_type

    @property
    def handle1(self):
        if len(self.handles) < 1:
            self.handles.add().get_temp_data()
        return self.handles[0]

    @property
    def handle2(self):
        if len(self.handles) < 2:
            if len(self.handles) < 1:
                self.handles.add().get_temp_data()
            self.handles.add().get_temp_data()
        return self.handles[1]

    @property
    def vertex0(self):
        return self.sketch.vertices[self.vertex_index[0]]

    @property
    def vertex1(self):
        return self.sketch.vertices[self.vertex_index[1]]

    def update(self):
        """Build this edge's own draw points and its length and box.

        These are the points of the curve the handles describe: what the editor
        draws and what the crossing search measures. The samples a mesh is built
        from are a pattern's own (`Pattern.sample_edge`), taken at that pattern's
        granularity from these same points, so nothing here depends on a pattern.
        """
        if not self.need_update_points:
            return
        self.vertices[0] = self.vertex0.co[:]
        self.vertices[1] = self.vertex1.co[:]
        self.render_points = self.generate_render_points(1024)
        # self.calc_length()
        pts = self.render_points
        self.length = np.sum(np.linalg.norm(pts[1:] - pts[:-1], axis=1))
        self.calc_bbox(pts)
        self.need_update_points = False
        if global_data.renderers_enabled:
            from ..gizmos.curve_renderer import CurveRenderer
            if self.renderer is None:
                self.renderer = CurveRenderer(self)
            self.renderer.update_batch()

    def calc_bbox(self, points):
        bbox_min = points.min(axis=0)
        bbox_max = points.max(axis=0)
        # bpy.context.workspace.status_text_set(f"{self.geo_points_temp.min(axis=0)} {self.geo_points_temp.max(axis=0)}")
        self.bbox[0] = bbox_min[0]
        self.bbox[1] = bbox_min[1]
        self.bbox[2] = bbox_max[0]
        self.bbox[3] = bbox_max[1]

    @property
    def type(self):
        return "BESSEL" if len(self.spline_points) == 0 else "CUBIC_SPLINE"

    @property
    def kind(self):
        """How this edge is drawn and sampled: straight, bezier or spline."""
        if len(self.spline_points) > 0:
            return "spline"
        if self.handle1_type == "VECTOR" and self.handle2_type == "VECTOR":
            return "straight"
        return "bezier"

    def set_curve(self, kind, handle1=None, handle2=None, points=None,
                  handle1_type=None, handle2_type=None):
        """Write this edge in one of the three forms the editor can hold.

        ``straight`` is a two-point edge with vector handles, ``bezier`` is a
        two-point edge with free (or aligned) handles, and ``spline`` is an
        interpolating curve through ``points``. The spline points are cleared
        for the other two kinds, so the written form is the one the kind asks
        for and nothing of the previous form is left behind.
        """
        if kind not in ("straight", "bezier", "spline"):
            raise ValueError(f"unknown edge kind {kind!r}")
        while len(self.spline_points) > 0:
            self.spline_points.remove(len(self.spline_points) - 1)
        if kind == "spline":
            for point in (points or ()):  # loop: one point object per control point
                handle = self.spline_points.add()
                handle.get_temp_data()
                handle.co = (float(point[0]), float(point[1]))
            handle1_type = handle1_type or "VECTOR"
            handle2_type = handle2_type or "VECTOR"
        elif kind == "straight":
            handle1_type = "VECTOR"
            handle2_type = "VECTOR"
        else:
            handle1_type = handle1_type or "FREE"
            handle2_type = handle2_type or "FREE"
        self.handle1.co = (float(handle1[0]), float(handle1[1])) if handle1 else (0.0, 0.0)
        self.handle2.co = (float(handle2[0]), float(handle2[1])) if handle2 else (0.0, 0.0)
        self.handle1_type = handle1_type
        self.handle2_type = handle2_type
        # The identity map has to name the wrappers the collection holds now:
        # adding an item retires the ones it handed out before, so the wrapper a
        # control point registered when it was made is not that point any more -
        # a pick reads an element back by identity and would find nothing.
        self.refresh_collection_uuid(self.handles)
        self.refresh_collection_uuid(self.spline_points)
        self.need_update_points = True
        sketch = self.sketch
        if sketch is not None:
            # One write path for "this edge is a line, a Bezier or a spline": the
            # Sketch tells every pattern that reads it that its geometry moved.
            sketch.geometry_written()
        return self

    def add_edge_point(self, position):
        point = self.spline_points.add()
        point.get_temp_data()
        point.co = position
        return point

    def generate_render_points(self, render_point_count=1024):
        h1 = None if self.handle1_type == "VECTOR" else self.handle1.co
        h2 = None if self.handle2_type == "VECTOR" else self.handle2.co
        edge_points = [p.co for p in self.spline_points]
        q = np.array((self.vertices[0], *edge_points, self.vertices[1]))
        return generate_curve_points(q, h1, h2, render_point_count).astype(np.float32)

    def raw_sections(self) -> list:
        """The Sketch's own pieces of this edge, in chain order.

        These are the first stage: spans and crossing marks only. What a pattern
        samples lives on that pattern's copy of this stage, not here.
        """
        sections = []
        section = self.section_start
        guard = 0
        while (section is not None and section is not self.section_end
               and guard < 10000):
            sections.append(section)
            section = section.next
            guard += 1
        if guard >= 10000:
            raise ValueError("Wrong section link!!")
        return sections

define_temp_prop(Edge2D, "sketch_temp", None)
define_temp_prop(Edge2D, "sketch_uuid", -1)
define_temp_prop(Edge2D, "length", None)
define_temp_prop(Edge2D, "vertices", lambda: [(0.0, 0.0), (0.0, 0.0)])
define_temp_prop(Edge2D, "need_update_points", True)
define_temp_prop(Edge2D, "render_points", None)
define_temp_prop(Edge2D, "renderer", None)
define_temp_prop(Edge2D, "section_start", None)
define_temp_prop(Edge2D, "section_end", None)
define_temp_prop(Edge2D, "proxy", None)

register, unregister = register_classes_factory((Vertex2D, Edge2D,))
