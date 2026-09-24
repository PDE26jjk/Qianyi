"""The Sketch: the authored vector geometry of a panel, one per instance chain.

A Sketch holds what a pattern maker draws - its vertices, its edges with their
handles and spline points, and its internal lines - together with the first
section stage built from them: one section per edge, the pieces every crossing
cuts those sections into, and which pieces of an internal line lie outside the
outline.

A write goes through this Sketch, and this Sketch is what marks the panels that
read it: one Sketch serves a whole instance chain, so one write reaches every
member and every member's derived data is out of date. Nothing here samples for a
mesh: the points the editor draws are the curves themselves, and the crossing
search measures on this Sketch's own samples, so a Sketch is decomposed the same
way whatever the granularity of the patterns that use it.
"""

from __future__ import annotations

import math

import numpy as np
from bpy.props import CollectionProperty, IntProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .. import global_data
from ..utilities.console import console
from ..utilities.curve_fit import polyline_length, resample_by_arc_length
from .geometry import Edge2D, Vertex2D
from .internal_line import InternalLine
from .model_data import ModelData, define_temp_prop, Selectable
from .section import SectionRaw

# The points the editor draws for one edge: parametric samples of the curve the
# handles were drawn to produce, which is what a draw point is.
DRAW_SAMPLES = 1024
# The parametric samples a measured edge is taken from before it is resampled
# at equal arc steps. Dense enough that the arc length of a curve is right, and
# fixed, so the measurement never follows a panel's granularity.
MEASURE_SAMPLES = 512
# How far apart the crossing search measures a curve, in millimetres, and the
# shortest piece it will cut: a piece below this would be merged away by any
# sampler, so cutting there would only add a section nothing can use.
MEASURE_STEP_MM = 0.5
MIN_PIECE_MM = 0.5
# A cap on the samples one edge contributes to the crossing search, so a very
# long curve cannot make the engine call unbounded.
MAX_MEASURE_POINTS = 20000


class Sketch(PropertyGroup, ModelData, Selectable):
    vertices: CollectionProperty(type=Vertex2D, name="vertices")
    edges: CollectionProperty(type=Edge2D, name="edges")
    internal_lines: CollectionProperty(type=InternalLine, name="internalLines")
    # The pattern that owns this Sketch. An instance chain shares one Sketch, so
    # the owner is the member that made it; a detach gives a member its own.
    owner_uuid: IntProperty(name="owner", default=-1, options={"HIDDEN"})

    # ------------------------------------------------------------- identity

    @property
    def owner(self):
        """The pattern that owns this Sketch, or None when it has none."""
        if self.owner_uuid == -1:
            return None
        pattern = global_data.get_obj_by_uuid(self.owner_uuid, check_uuid=False)
        if pattern is not None:
            return pattern
        # Undo, redo and a file reload clear the identity map, and a panel that
        # owns a Sketch has to be found again without one: the project's own
        # collection is the other half of the reference.
        for candidate in self.id_data.patterns:  # loop: one comparison per panel
            if candidate.global_uuid == self.owner_uuid:
                global_data.uuid2obj[self.owner_uuid] = candidate
                return candidate
        return None

    @owner.setter
    def owner(self, pattern):
        self.owner_uuid = pattern.global_uuid if pattern is not None else -1

    def geometry_written(self) -> int:
        """A write went in: tell every panel that reads this Sketch about it.

        Every write path of this Sketch ends here. A write through the Sketch is
        a write for the whole instance chain, so each panel that reads it gets
        the signal a tool sends after an edit of its own: its outline state, its
        own copy of the stage, its samples, its render line and the sewings that
        reach it (`Pattern.mark_geometry_changed`). Returns how many panels were
        told.
        """
        told = 0
        for pattern in self.reading_patterns():  # loop: one signal per panel
            pattern.mark_geometry_changed()
            told += 1
        return told

    def reading_patterns(self) -> list:
        """Every panel that reads this Sketch, in the project's own order.

        A panel belongs to the Sketch it names and to no other, so this is the
        instance chain: one entry for a panel that was never copied, all of them
        for a chain. An edit written here is an edit of every one, which is why
        the signals below are sent to the list rather than to a single panel.
        """
        project = self.id_data
        return [pattern for pattern in project.patterns
                if pattern.sketch_uuid == self.global_uuid]

    def rebuild_meshes(self) -> int:
        """Build the mesh of every panel that reads this Sketch.

        The meshes are not shared: a panel samples the geometry of the chain at
        its own granularity and keeps its own mesh object, so an edit of the
        Sketch leaves one stale mesh per member. A tool that changed the
        topology calls this after its write, because what the editor draws is
        the mesh - a member left marked would show the shape that used to be
        there until something else meshed it.

        A panel with nothing marked keeps the mesh it has (`generate_mesh` is a
        no-op for it), so a caller does not have to sort the members out first.
        Returns how many members were asked.
        """
        told = 0
        for pattern in self.reading_patterns():  # loop: one mesh per member
            pattern.generate_mesh()
            told += 1
        return told

    def initialize(self) -> None:
        """Build the draw points of the elements this Sketch holds."""
        for line in self.internal_lines:  # loop: one per internal line
            line.initialize()
        self.update_draw_points()

    # ------------------------------------------------------------- elements

    def own(self, element):
        """Give one element its identity and record this Sketch as its own.

        An element is created inside a Sketch and is written through right away,
        while adding to the collection the Sketch holds retires every wrapper it
        handed out before - a retired wrapper cannot read its own path, which is
        how an element knows where it lives. So the Sketch is recorded here, and
        `element.sketch` answers from that record for as long as the element
        exists.
        """
        element.get_temp_data()
        element.sketch_temp = self
        element.sketch_uuid = self.global_uuid
        return element

    def add_vertex(self, position) -> int:
        """Add one point and return its index in this Sketch."""
        vertex = self.own(self.vertices.add())
        vertex.co = position
        self.mark_curves_changed()
        self.geometry_written()
        return len(self.vertices) - 1

    def copy(self, owner=None) -> "Sketch":
        """A private copy of this Sketch, for a pattern that leaves its chain.

        Points, edges (with their handles and spline points) and internal lines
        come along in the same order and index the same points, so the copy
        reads like the Sketch it came from.
        """
        new: Sketch = self.id_data.add_sketch(owner=owner)
        for vertex in self.vertices:  # loop: one point object per point
            new.add_vertex((vertex.co[0], vertex.co[1]))
        for edge in self.edges:  # loop: one edge object per edge
            self._copy_edge(new, new.edges, edge)
        new.refresh_collection_uuid(new.edges)
        for line in self.internal_lines:  # loop: one line object per line
            target_line: InternalLine = new.internal_lines.add()
            target_line.get_temp_data()
            target_line.is_loop = line.is_loop
            target_line.is_hole = line.is_hole
            target_line.name = line.name
            for edge in line.edges:  # loop: one edge object per line edge
                self._copy_edge(new, target_line.edges, edge)
            new.refresh_collection_uuid(target_line.edges)
        new.owner = owner
        new.initialize()
        new.update()
        return new

    @staticmethod
    def _copy_edge(sketch, edges, edge) -> None:
        """Write one edge of this Sketch into `edges` as `edge` is drawn."""
        target: Edge2D = sketch.own(edges.add())
        target.vertex_index[0] = edge.vertex_index[0]
        target.vertex_index[1] = edge.vertex_index[1]
        handle1 = edge.handle1.co[:] if len(edge.handles) > 0 else (0.0, 0.0)
        handle2 = edge.handle2.co[:] if len(edge.handles) > 1 else (0.0, 0.0)
        # One implementation of "write this edge as a line, a Bezier or a
        # spline", so a copy cannot drift from what the editor writes.
        target.set_curve(edge.kind, handle1, handle2,
                         [(point.co[0], point.co[1]) for point in edge.spline_points],
                         edge.handle1_type, edge.handle2_type)
        target.name = edge.name

    def set_vertex_position(self, index, position) -> bool:
        """Move one point to `position`; True when the Sketch changed.

        A write that puts the point where it already is changes nothing, and so
        sends no signal: nothing about the shape moved.
        """
        vertex = self.vertices[index]
        target = (float(position[0]), float(position[1]))
        if (round(float(vertex.co[0]), 9), round(float(vertex.co[1]), 9)) == (
                round(target[0], 9), round(target[1], 9)):
            return False
        vertex.co = target
        self.mark_curves_changed()
        self.geometry_written()
        return True

    def add_edge(self, start_idx, end_idx, control1=None, control2=None,
                 handle1_type="VECTOR", handle2_type="VECTOR",
                 update=True) -> Edge2D:
        """Add one edge between two of this Sketch's points."""
        edge: Edge2D = self.own(self.edges.add())
        edge.vertex_index[0] = start_idx
        edge.vertex_index[1] = end_idx
        if control1 is not None and control2 is not None:
            edge.handle1.co = control1[:]
            edge.handle2.co = control2[:]
        edge.handle1_type = handle1_type
        edge.handle2_type = handle2_type
        self.mark_curves_changed()
        self.geometry_written()
        return edge

    def add_internal_line(self, segments, is_loop=False) -> InternalLine:
        """Add one internal line from a run of curve pieces.

        ``segments`` is a list of dicts with ``p0``, ``p1`` (in pattern space,
        millimetres), ``h1``, ``h2``, ``h1_type`` and ``h2_type``; consecutive
        pieces share their end point the way the internal line pen draws them,
        and the points become vertices of this Sketch.
        """
        if not segments:
            raise ValueError("an internal line needs at least one segment")
        line: InternalLine = self.own(self.internal_lines.add())
        line.is_loop = bool(is_loop)
        offset = len(self.vertices)
        for segment in segments:  # loop: one vertex object per curve piece
            self.add_vertex(segment["p0"])
        if not is_loop:
            self.add_vertex(segments[-1]["p1"])
        for index, segment in enumerate(segments):  # loop: one edge per piece
            if is_loop:
                next_index = (index + 1) % len(segments)
            else:
                next_index = index + 1
            line.add_edge(index + offset, next_index + offset,
                          segment["h1"], segment["h2"],
                          segment.get("h1_type", "VECTOR"),
                          segment.get("h2_type", "VECTOR"), update=False)
        line.initialize()
        self.mark_curves_changed()
        self.update()
        self.geometry_written()
        return line

    # ---------------------------------------------------------- draw points

    def mark_curves_changed(self) -> None:
        """The curves moved: the drawn points of every edge are stale.

        Marking, not rebuilding: an edge builds its own points - and with them
        its length, its box and its render batch - the next time `Edge2D.update`
        is asked for them, which the draw path, the outline test and the
        measuring passes all do before they read one.
        """
        for edge in self.all_edges():  # loop: one flag per edge
            edge.need_update_points = True

    def update_draw_points(self) -> None:
        """Build every edge's own draw points from its curve.

        Deliberately not the samples a mesh is built from: these are the points
        of the curves as drawn, so the editor shows the shape the pattern maker
        made whatever sampling size a panel uses.
        """
        for edge in self.all_edges():  # loop: one RNA array write per edge
            points = self.edge_points(edge, DRAW_SAMPLES)
            edge.render_points = points
            edge.length = float(np.sum(np.linalg.norm(points[1:] - points[:-1], axis=1)))
            edge.calc_bbox(points)

    def all_edges(self) -> list:
        """Every edge of this Sketch: the outline first, then the lines' own."""
        edges = list(self.edges)
        for line in self.internal_lines:  # loop: one collection per line
            edges.extend(line.edges)
        return edges

    def edge_points(self, edge, count=DRAW_SAMPLES) -> np.ndarray:
        """One edge's curve points, from where its two ends are now.

        The cached ends an edge carries are refreshed first: a line's edges are
        read the same way the outline's are, and a stale cache would otherwise
        measure the curve where it used to be.
        """
        sketch = edge.sketch
        if sketch is None or len(sketch.vertices) == 0:
            raise RuntimeError(
                f"{edge.path_from_id()} has no points to read: its owner holds "
                f"{0 if sketch is None else len(sketch.vertices)} of them")
        edge.vertices[0] = edge.vertex0.co[:]
        edge.vertices[1] = edge.vertex1.co[:]
        return edge.generate_render_points(count)

    def draw_points(self) -> np.ndarray:
        """Every edge's draw points in outline order, as one ``(N, 2)`` array."""
        chunks = [np.asarray(edge.render_points, dtype=np.float32)
                  for edge in self.edges if edge.render_points is not None]
        if not chunks:
            return np.zeros((0, 2), dtype=np.float32)
        return np.concatenate(chunks)

    def measured_points(self, edge) -> np.ndarray:
        """One edge measured at equal arc steps, for the crossing search.

        The step is the Sketch's own constant, not a panel's granularity: which
        pieces a Sketch is cut into must not move when the sampling size of the
        patterns using it changes.
        """
        points = self.edge_points(edge, MEASURE_SAMPLES)
        length = polyline_length(points)
        count = int(math.ceil(length / MEASURE_STEP_MM)) + 1
        count = min(max(count, 2), MAX_MEASURE_POINTS)
        return resample_by_arc_length(points, count)

    # ------------------------------------------------------ section stage

    def recreate_sections(self) -> None:
        """The first stage: one section per edge, linked along its chain.

        The outline is one closed chain; each internal line is its own chain,
        closed for a loop and open otherwise. Every piece knows the edge it
        belongs to and its own span of that edge, so a later cut only has to
        split the piece it lands in.

        What is stored is `SectionRaw`: a span and its crossing marks. Nothing a
        panel samples is written here - a panel clones this stage into its own
        pieces before it samples anything.
        """
        for edge in self.edges:
            edge.section_start = SectionRaw(edge, 0., 1.)
        for i, edge in enumerate(self.edges):
            next_sec = self.edges[(i + 1) % len(self.edges)].section_start
            prev_sec = self.edges[(i - 1) % len(self.edges)].section_start
            edge.section_start.next = next_sec
            edge.section_start.prev = prev_sec
            edge.section_end = next_sec
        for line in self.internal_lines:
            for edge in line.edges:
                edge.section_start = SectionRaw(edge, 0., 1.)
            if line.is_loop:
                for i, edge in enumerate(line.edges):
                    next_sec = line.edges[(i + 1) % len(line.edges)].section_start
                    prev_sec = line.edges[(i - 1) % len(line.edges)].section_start
                    edge.section_start.next = next_sec
                    edge.section_start.prev = prev_sec
                    edge.section_end = next_sec
            else:
                for i, edge in enumerate(line.edges):
                    last = i == len(line.edges) - 1
                    next_sec = None if last else line.edges[i + 1].section_start
                    prev_sec = None if i == 0 else line.edges[i - 1].section_start
                    edge.section_start.next = next_sec
                    edge.section_start.prev = prev_sec
                    edge.section_end = next_sec

    def line_sections(self, line) -> list:
        """Every section of one internal line, in chain order."""
        if len(line.edges) == 0:
            return []
        sections = []
        sec = line.edges[0].section_start
        guard = 0
        while sec is not None and sec not in sections and guard < 100000:
            sections.append(sec)
            sec = sec.next
            guard += 1
        return sections

    def cut_at_crossings(self) -> int:
        """Cut the first-stage sections where the curves cross each other.

        Every crossing between the outline and an internal line, and every
        crossing between two internal lines, splits the sections of both curves
        there, and the run of an internal line that lies outside the outline is
        marked as outside. Returns how many crossings were applied.

        Reads the sections as the first stage left them (one per edge), which is
        what `update` guarantees before this runs.
        """
        if len(self.internal_lines) == 0 or len(self.edges) == 0:
            return 0
        from Qianyi_DP import pattern_helper

        curves = [self.edges] + [line.edges for line in self.internal_lines]
        # What each section contributes to the engine's point array: the edge's
        # own samples minus the end it shares with the next piece, which is the
        # same layout the mesh path hands over, so a returned (section, t) reads
        # the way the engine means it.
        runs = []
        curve_sizes = []
        for curve_index, edges in enumerate(curves):
            is_loop = curve_index == 0 or self.internal_lines[curve_index - 1].is_loop
            size = 0
            for index, edge in enumerate(edges):  # loop: one run per section
                points = self.measured_points(edge)
                last = not is_loop and index == len(edges) - 1
                run = points if last else points[:-1]
                runs.append(run)
                size += len(run)
            curve_sizes.append(size)
        points = np.concatenate(runs).astype(np.float32)
        curve_sizes = np.array(curve_sizes, dtype=np.int32)
        is_loops = np.array([1, *[int(line.is_loop) for line in self.internal_lines]],
                            dtype=np.int8)
        section_sizes = np.array([len(edges) for edges in curves], dtype=np.int32)
        section_points = np.array([len(run) for run in runs], dtype=np.int32)
        intersections = pattern_helper.get_all_intersections(
            points, curve_sizes, is_loops, section_sizes, section_points)
        if len(intersections) == 0:
            return 0
        pending = {}  # section -> [(t, state), ...]
        for intersection in intersections:  # loop: one entry per crossing
            for curve, section_index, t, state in (
                    (intersection["curve_a"], intersection["section_a"],
                     intersection["t_a"], 0),
                    (intersection["curve_b"], intersection["section_b"],
                     intersection["t_b"], intersection["state"])):
                section = curves[curve][section_index].section_start
                pending.setdefault(section, []).append((float(t), int(state)))
        for section, cuts in pending.items():  # loop: one split per cut section
            self._split_section(section, cuts)
        self.mark_outside()
        return len(intersections)

    def _split_section(self, section, cuts) -> None:
        """Cut one section at these ``(t, state)`` positions, lowest first.

        The same splice the pattern path uses, with the shortest-piece guard
        measured on this Sketch instead of on a panel's granularity: a cut
        closer than `MIN_PIECE_MM` to the one before it is the same crossing.
        """
        length = section.end_pos - section.start_pos
        # A length is what the last draw pass measured; an edge that has not been
        # measured yet counts as having no room to guard, which cuts everything.
        absolute = length * float(section.edge.length or 0.0)
        minimum = MIN_PIECE_MM / absolute if absolute > 0 else 0.0
        end_pos = section.end_pos
        start_pos = section.start_pos
        piece = section
        last = 0.0
        for t, state in sorted(cuts, key=lambda entry: entry[0]):
            if t - last < minimum:
                if state != 0:
                    piece.io_state = state
                continue
            cut_pos = start_pos + length * t
            # The piece being cut ends where the cut is: the new piece takes
            # over everything above. Without this the lower piece keeps the
            # whole span and reads as long as the edge it came from, which is
            # what gave a short piece a segment count measured on the whole
            # edge - a piece of a few millimetres sampled as densely as the
            # entire edge.
            piece.end_pos = cut_pos
            new_sec = SectionRaw(section.edge, cut_pos, end_pos)
            new_sec.io_state = state
            new_sec.outsize = piece.outsize
            new_sec.next = piece.next
            new_sec.prev = piece
            if new_sec.next is not None:
                new_sec.next.prev = new_sec
            piece.next = new_sec
            piece = new_sec
            last = t

    def mark_outside(self) -> int:
        """Mark the pieces of every internal line that lie outside the outline.

        A crossing that enters the outline is state 2 and one that leaves is
        state 1, so the run before the first entry, the run after the last exit
        and every run between an exit and the next entry are outside. Returns
        how many pieces were marked.
        """
        marked = 0
        for line in self.internal_lines:  # loop: one chain per internal line
            sections = self.line_sections(line)
            if not sections:
                continue
            crossings = [index for index, section in enumerate(sections)
                         if section.io_state != 0]
            for index, section in enumerate(sections):
                section.outsize = False
            if not crossings:
                continue
            if sections[crossings[0]].io_state == 2:
                for section in sections[:crossings[0]]:
                    section.outsize = True
                    marked += 1
            if sections[crossings[-1]].io_state == 1:
                for section in sections[crossings[-1]:]:
                    section.outsize = True
                    marked += 1
            for index in range(len(crossings) - 1):
                if sections[crossings[index]].io_state != 1:
                    continue
                for section in sections[crossings[index]:crossings[index + 1]]:
                    section.outsize = True
                    marked += 1
        return marked

    def update(self) -> None:
        """Build everything this Sketch owns, from the curves as they are now.

        That is the identity of its elements, the draw points of its edges - the
        points the editor shows, which are the curves themselves - and its first
        section stage: one section per edge, cut where the curves cross, with the
        pieces of an internal line that lie outside the outline marked as
        outside. Nothing here samples for a mesh, and nothing here belongs to a
        single panel: the panels that use this Sketch copy the stage and take
        their own samples from the copy.

        It is derived work, so it sends no signal of its own: rebuilding the
        stage is driven by a caller - a panel that was marked asks for it.
        """
        self.refresh_collection_uuid(self.vertices)
        self.refresh_collection_uuid(self.edges)
        for line in self.internal_lines:  # loop: one identity set per line
            self.refresh_collection_uuid(line.edges)
        self.update_draw_points()
        self.recreate_sections()
        self.cut_at_crossings()


define_temp_prop(Sketch, "renderer", None)

register, unregister = register_classes_factory((Sketch,))
