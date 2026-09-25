import bpy
import numpy as np
import random
from bpy.utils import register_classes_factory

from ..utilities.console import console
from .. import global_data
from .pattern import Pattern

from .fabric import Fabric
from .generator import (PatternGenerator, generator_of_pattern,
                        refresh_generators)
from .model_data import ModelData, define_temp_prop, owner_pattern
from .sewing import Sewing, calc_sewing_sections
from .sketch import Sketch
from ..declarations import Panels


def outline_sample_counts(pattern) -> tuple:
    """How many outline points the edge finder takes from each edge of a panel.

    Each edge contributes its samples except the last one - the outline is a
    loop, so an edge's last sample is the next edge's first, which is what
    `Pattern.get_geo_points_unique` hands the finder. The panel is brought up to
    date first: the counts are compared against the snapshot the finder took,
    and a marked panel has to answer with the shape it has now. One number per
    edge and not the total: a split moves the points from one edge onto two
    without changing how many there are.
    """
    pattern.ensure_sections()
    counts = []
    for index in range(len(pattern.edges)):  # loop: one run per outline edge
        points = pattern.sample_points.get((None, index))
        if points is None:
            raise ValueError(f"panel {pattern.name or '(unnamed)'} has no samples "
                             f"for its edge {index}")
        counts.append(max(len(points) - 1, 0))
    return tuple(counts)


def section_grid(pattern):
    """A cheap signature of the piece grid the mesh is sampled from.

    Every piece's boundaries and segment count decide the sampled points, so
    two equal signatures mean the same mesh. Used to tell whether a linking run
    actually changed a panel before spending a triangulation on it.
    """
    grid = []
    groups = [(None, pattern.edges)]
    groups.extend((index, line.edges)
                  for index, line in enumerate(pattern.internal_lines))
    for key, edges in groups:  # loop: the outline first, then the internal lines
        for index, edge in enumerate(edges):
            # The geometry counts too: a moved vertex or handle changes the
            # samples even when the piece grid stays as it is.
            grid.append(("edge", int(edge.vertex_index[0]), int(edge.vertex_index[1]),
                         round(float(edge.length or 0.0), 6)))
            # The pieces are this panel's own copy of the Sketch's stage: two
            # panels of one chain may have been cut differently by their seams,
            # and it is the panel's own grid that decides its mesh.
            for section in pattern.sections_for_edge(key, index):
                grid.append((round(section.start_pos, 6), round(section.end_pos, 6),
                             section.seg))
    return tuple(grid)


def library_category_items(self=None, context=None):
    """Categories offered by the panel library, evaluated when the UI asks."""
    from ..panellib import registry

    items = [("ALL", "All", "Every panel component")]
    try:
        categories = sorted({info.category for info in registry.infos()})
    except Exception:
        categories = []
    items.extend((category.upper(), category, "") for category in categories)
    return items


class UuidType(bpy.types.PropertyGroup):
    uuid: bpy.props.IntProperty(default=-1)


def get_unique_name(collection, base_name):
    if base_name not in collection:
        return base_name

    i = 1
    while f"{base_name}.{i:03d}" in collection:
        i += 1
    return f"{base_name}.{i:03d}"


def normalize_sewing_color(color):
    """The RGB a sewing is drawn with.

    A caller (a script, an importer) can pass its own (r, g, b) or (r, g, b, a)
    tuple; without one the sewing gets a random but saturated color, so adjacent
    chains are told apart instead of every one of them being white.
    """
    if color is None:
        import colorsys

        r, g, b = colorsys.hsv_to_rgb(random.random(), 0.7, 1.0)
        return (r, g, b)
    values = [float(value) for value in color]
    if len(values) < 3:
        raise ValueError(f"sewing color needs at least three components, got {color!r}")
    return tuple(max(0.0, min(1.0, value)) for value in values[:3])


def edge_click_fraction(edge, point):
    """Where along an edge a point sits: 0.0 at its start, 1.0 at its end."""
    points = edge.render_points
    if points is None or len(points) < 2:
        return 0.0
    delta_x = points[:, 0] - float(point[0])
    delta_y = points[:, 1] - float(point[1])
    return float(np.argmin(delta_x * delta_x + delta_y * delta_y)) / (len(points) - 1)


def sewing_half_directions(edge1, point1, edge2, point2):
    """``(pos1, pos2, reverse)`` for both halves of a one-to-one sewing.

    Each click only says which of its edge's two ends is nearer. When both
    clicks are near the same end - both first or both second - both halves run
    from their edge's first point to its second and nothing is flipped. When
    the clicks are near different ends the second half is flipped: it runs from
    its second point back to its first.

    `reverse` is the flip: False follows the edge's vertex order, True walks
    against it. A flipped half is also the one that has to leave its edge
    through the second point, otherwise the section walk would go the long way
    round the pattern.
    """
    first_of_edge1 = edge_click_fraction(edge1, point1) < 0.5
    first_of_edge2 = edge_click_fraction(edge2, point2) < 0.5
    if first_of_edge1 == first_of_edge2:
        return (0.0, 1.0, False), (0.0, 1.0, False)
    return (0.0, 1.0, False), (1.0, 0.0, True)


def edge_point_at(edge, position):
    """The edge end a half-sewing position refers to."""
    points = edge.render_points
    if points is None or len(points) < 2:
        return (0.0, 0.0)
    return points[0] if position < 0.5 else points[-1]


class QianyiProject(bpy.types.NodeTree, ModelData):
    """ Qianyi Project for editor, a NodeTree"""
    bl_label = "Qianyi Project"
    bl_icon = 'FILE_SCRIPT'
    bl_idname = Panels.QianyiNodeTree

    patterns: bpy.props.CollectionProperty(
        type=Pattern,
        name="patterns",
        description="The patterns of this project",
    )

    sewings: bpy.props.CollectionProperty(
        type=Sewing,
        name="sewings",
        description="The sewings of this project",
    )
    fabrics: bpy.props.CollectionProperty(
        type=Fabric,
        name="fabrics",
        description="The fabrics of this project",
    )
    generators: bpy.props.CollectionProperty(
        type=PatternGenerator,
        name="generators",
        description="Parametric panel generators of this project",
    )

    sketches: bpy.props.CollectionProperty(
        type=Sketch,
        name="sketches",
        description="The authored vector geometry of this project's panels. One "
                    "Sketch is shared by every member of an instance chain.",
    )

    active_pattern_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active Pattern",
        description="The project editing",
        # update=update_active_pattern_index,
    )
    active_fabric_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active fabric",
        description="The project editing",
        # update=update_active_fabric_index,
    )
    active_generator_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active generator",
        description="The generator shown in the library panel",
    )
    library_filter: bpy.props.StringProperty(
        name="Search",
        default="",
        description="Filter the panel library by name, category or description",
    )
    library_category: bpy.props.EnumProperty(
        name="Category",
        items=library_category_items,
        description="Show only components of this category",
    )
    library_component_id: bpy.props.StringProperty(
        name="Selected component",
        default="",
        description="Component shown in the library's detail area",
    )

    # Silhouette guide: objects projected into the pattern window as an
    # alignment background. Display only - nothing here is meshed, simulated or
    # written into the engine payload.
    show_silhouette: bpy.props.BoolProperty(
        name="Show Silhouette",
        description="Draw the silhouette of the collection below behind the "
                    "panels of the pattern editor",
        default=False,
    )
    silhouette_collection: bpy.props.PointerProperty(
        type=bpy.types.Collection,
        name="Objects",
        description="Collection projected into the pattern window as an "
                    "alignment background (typically the body)",
    )
    silhouette_axis: bpy.props.EnumProperty(
        name="View",
        description="World axis the silhouette is projected along",
        items=[
            ('X', "Side (X)", "Project along X, so the body is seen from its side"),
            ('Y', "Front (Y)", "Project along Y, so the body is seen from the front"),
            ('Z', "Top (Z)", "Project along Z, so the body is seen from above"),
        ],
        default='Y',
    )
    silhouette_offset: bpy.props.FloatVectorProperty(
        name="Offset",
        description="Move the silhouette within the pattern window, in millimetres",
        size=2,
        default=(0.0, 0.0),
    )
    silhouette_color: bpy.props.FloatVectorProperty(
        name="Color",
        description="Colour the silhouette is drawn with",
        subtype='COLOR',
        size=3,
        default=(0.35, 0.35, 0.40),
        min=0.0,
        max=1.0,
    )
    silhouette_opacity: bpy.props.FloatProperty(
        name="Fill Opacity",
        description="Opacity of the filled silhouette",
        default=0.25,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )
    silhouette_show_mesh: bpy.props.BoolProperty(
        name="Mesh",
        description="Also draw the projected mesh edges over the fill",
        default=True,
    )
    silhouette_mesh_opacity: bpy.props.FloatProperty(
        name="Mesh Opacity",
        description="Opacity of the projected mesh edges",
        default=0.35,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )

    index: bpy.props.IntProperty(
        default=-1,
        description="The index of this node tree in the node tree list",
        name="Index",
    )

    selected_patterns: bpy.props.CollectionProperty(type=UuidType)
    selected_vertices: bpy.props.CollectionProperty(type=UuidType)
    selected_edges: bpy.props.CollectionProperty(type=UuidType)
    selected_sewings: bpy.props.CollectionProperty(type=UuidType)

    # def update(self):
    #     pass
    #
    def calc_all_sewings_sections(self):
        self.refresh_collection_uuid(self.sewings)
        # Start every recompute from fresh sections.
        #
        # The link id lives on the Section object, while the list those ids
        # index into (`Section.link_sections`) is cleared at the start of
        # calc_sewing_sections. Linking sections that still carry an id from
        # the previous run therefore fails: two sections that happen to share
        # an id raise "Sewing overlap!!!" even though the sewing is valid, and
        # different ids walk into the list that was just emptied. It also needs
        # the edge geometry (length, sampled points, sections) built, which a
        # freshly opened file or a just created pattern does not have yet -
        # that used to fail inside with a NoneType error. Marking the panels
        # says their copies are stale, and the linking run builds each copy
        # here - which refreshes the Sketch's own stage first - so this is that
        # sequence for the sewings the editor is about to link.
        for pattern in self.sewing_patterns():
            pattern.mark_geometry_changed()
            # The copies the linking run is about to cut are built here, before
            # it starts: a rebuild in the middle of that run would leave the
            # halves it already linked pointing at pieces that are gone.
            pattern.ensure_sections()
        calc_sewing_sections(self.sewings)
        for p in self.patterns:
            p.need_sewing_update = False

    def sewing_patterns(self):
        """Every pattern the current sewings touch, each one once."""
        patterns = []
        seen = set()
        for sewing in self.sewings:
            for pattern in self.sewing_patterns_of(sewing):
                if pattern.global_uuid in seen:
                    continue
                seen.add(pattern.global_uuid)
                patterns.append(pattern)
        return patterns

    @property
    def active_pattern(self):
        """The panel the pattern list is on, or None when there is none.

        The tools that need "which panel is this about" read it here: selecting
        an element of a member of a chain makes that member active, so the panel
        and the tool always talk about the same one.
        """
        index = int(self.active_pattern_index)
        if 0 <= index < len(self.patterns):
            return self.patterns[index]
        return None

    def set_active_pattern(self, pattern) -> bool:
        """Make one panel the active one; False when it is not in the project."""
        if pattern is None:
            return False
        for index, candidate in enumerate(self.patterns):  # loop: one per panel
            if candidate.global_uuid == pattern.global_uuid:
                self.active_pattern_index = index
                return True
        return False

    def calc_sewings_sections(self, sewings):
        calc_sewing_sections(sewings)

    def get_default_fabric(self):
        if len(self.fabrics) < 1:
            fabric = self.fabrics.add()
            # The fabric is named by uuid wherever a panel refers to it, so it
            # gets its identity as soon as it exists.
            fabric.get_temp_data()
            fabric.name = "Default Fabric"
            self.refresh_collection_uuid(self.fabrics)
        return self.fabrics[0]

    def clear_temp_data(self):
        self.initialized = False

    def update_all(self, forced=False):
        if not self.initialized or forced:
            for p in self.patterns:
                f = p.fabric
            self.initialized = True
        # for p in self.patterns:
        #     p.mark_geometry_changed()

    def get_selected_objects_by_mode(self, mode, submode=None, strict=True):
        """Every object selected in `mode`, whatever mode the editor is in.

        The selection is kept per mode, so a caller that asks for a mode other
        than the current one gets the elements that mode left selected - which
        is what lets a selection outlive a mode switch. `submode` only narrows
        the edge mode further; leaving it out returns its edges and vertices.

        An entry whose data is gone is skipped rather than returned as None.
        `strict` decides what a shifted identity does: the editing callers keep
        seeing it as an error, while the drawing path asks for the tolerant
        lookup, because a selection that outlived the element it names must not
        fail a redraw.
        """
        if mode == "PATTERN":
            uuids = [entry.uuid for entry in self.selected_patterns]
        elif mode == "EDGE":
            if submode not in (None, "EDGE_VERTEX"):
                return []
            uuids = [entry.uuid for entry in self.selected_edges]
            for entry in self.selected_vertices:  # loop: one RNA read per item
                uuids.append(entry.uuid)
        elif mode == "SEWING":
            uuids = [entry.uuid for entry in self.selected_sewings]
        else:
            return []
        selected_objects = []
        for uuid in uuids:  # loop: one identity lookup per selected element
            obj = global_data.get_obj_by_uuid(uuid, check_uuid=strict)
            if obj is not None:
                selected_objects.append(obj)
            else:
                self.clear_selected_objects_by_mode(mode)
                return []
        return selected_objects

    def forget_selected(self, uuids) -> int:
        """Drop these identities from every selection this project keeps.

        A command that removes an element leaves the selection naming it: the
        element is gone, so nothing can be drawn for it and every reader of the
        selection has to skip it. Saying which identities went is the removal's
        own business, and this is how it says it. Returns how many entries went.
        """
        gone = {int(uuid_value) for uuid_value in uuids}
        dropped = 0
        for collection in (self.selected_vertices, self.selected_edges,
                           self.selected_patterns, self.selected_sewings):
            # loop: one entry per selected identity of this collection
            indexes = [index for index, entry in enumerate(collection)
                       if int(entry.uuid) in gone]
            for index in sorted(indexes, reverse=True):  # loop: RNA removes per item
                collection.remove(index)
                dropped += 1
        return dropped

    def clear_selected_objects_by_mode(self, mode):
        if mode == "PATTERN":
            self.selected_patterns.clear()
        elif mode == "EDGE":
            self.selected_edges.clear()
            self.selected_vertices.clear()
        elif mode == "SEWING":
            self.selected_sewings.clear()

    def add_sewing(self, side1_line1, side1_pos1, side1_line2, side1_pos2, side1_reverse,
                   side2_line1, side2_pos1, side2_line2, side2_pos2, side2_reverse, update=True,
                   color=None, pattern1=None, pattern2=None):
        """Add one sewing; `pattern1` / `pattern2` name the panels it is made on.

        The edges alone cannot say that: one edge serves every member of its
        instance chain. A caller that does not name a panel gets the one that
        owns the edge's Sketch - the chain's first member - and that is what the
        seam records; a caller making a seam on a copy names that copy.
        """
        if pattern1 is None:
            pattern1 = owner_pattern(side1_line1)
        if pattern2 is None:
            pattern2 = owner_pattern(side2_line1)
        if pattern1 is None or pattern2 is None:
            self.last_sewing_error = ("a seam needs the panel of each side, and "
                                      "these edges name none")
            return None
        sw = self.sewings.add()
        sw.side1.update_data(side1_line1, side1_pos1, side1_line2, side1_pos2, side1_reverse,
                             pattern1)
        sw.side2.update_data(side2_line1, side2_pos1, side2_line2, side2_pos2, side2_reverse,
                             pattern2)
        sw.color = normalize_sewing_color(color)
        if update:
            try:
                # Every panel a sewing touches has its copy built here, before
                # the linking run reads pieces: a copy that was marked but never
                # rebuilt still holds pieces whose edge an earlier edit replaced,
                # and the run walks every sewing, not only this one. The meshes
                # are not rebuilt: a seam edit meshes nothing.
                self.calc_all_sewings_sections()
                sw.update()
            except Exception as e:
                console.warning("Failed to add sewing: ", e)
                self.sewings.remove(len(self.sewings) - 1)
                # Keep the reason: the add-sewing operator used to show
                # "sewing overlap!" for every failure, which hid a missing
                # section, a missing edge length and a real overlap behind the
                # same message.
                self.last_sewing_error = str(e)
                return None
        self.refresh_collection_uuid(self.sewings)
        sw.pattern1.need_sewing_update = True
        sw.pattern2.need_sewing_update = True
        return sw

    @staticmethod
    def sewing_patterns_of(sewing):
        """The patterns a sewing joins, in a stable order."""
        patterns = []
        for side in (sewing.side1, sewing.side2):
            # The panel the side was made on, by identity: a side whose panel an
            # editor removed reads back as None.
            pattern = side.pattern
            if pattern is not None and pattern not in patterns:
                patterns.append(pattern)
        return patterns

    def add_sewing1to1(self, edge1, edge2, reverse=False, color=None,
                       pattern1=None, pattern2=None):
        first_half = (0.0, 1.0, False)
        second_half = (0.0, 1.0, False) if not reverse else (1.0, 0.0, True)
        return self.add_sewing(edge1, first_half[0], edge1, first_half[1], first_half[2],
                               edge2, second_half[0], edge2, second_half[1], second_half[2],
                               color=color, pattern1=pattern1, pattern2=pattern2)

    def add_sewing1to1_from_points(self, edge1, point1, edge2, point2, color=None,
                                   pattern1=None, pattern2=None):
        """One-to-one sewing whose direction follows where the edges were clicked.

        `point1` / `point2` are the click positions in the pattern space of
        their edge. Clicks near the same end of both edges keep the original
        pairing; clicks near different ends flip the second half - which is the
        only way this editor can express the two stitch directions. The panels
        the clicks were made on are passed with them, because the edges do not
        say which member of an instance chain a seam belongs to.
        """
        first_half, second_half = sewing_half_directions(edge1, point1, edge2, point2)
        return self.add_sewing(edge1, first_half[0], edge1, first_half[1], first_half[2],
                               edge2, second_half[0], edge2, second_half[1], second_half[2],
                               color=color, pattern1=pattern1, pattern2=pattern2)

    def setup_sewings_for_simulation(self):
        # self.calc_all_sewings_sections()
        # recalculate all sewings if needed.
        for pattern in self.patterns:
            if pattern.need_sewing_update:
                connected_patterns, involved_sewings = pattern.get_connected_patterns_and_sewings()
                grids = {}
                for p in connected_patterns:
                    p.mark_geometry_changed()
                    # The mesh is sampled from the piece grid, so this is what
                    # says whether a panel has to be triangulated again. It is
                    # taken after the resample and compared after the link, so
                    # a panel the linking run did not cut keeps its mesh -
                    # `generate_pattern_mesh` is the single most expensive step
                    # here (about 90 ms per panel).
                    grids[p] = section_grid(p)
                self.calc_sewings_sections(involved_sewings)
                for p in connected_patterns:
                    p.need_sewing_update = False
                    rebuild = p.mesh_object is None or section_grid(p) != grids[p]
                    if global_data.renderers_enabled and p.mesh_renderer is None:
                        # A panel that lost its render batch (reload, undo) has
                        # to go through `generate_mesh` again to get one.
                        rebuild = True
                    if rebuild:
                        p.generate_mesh()

        sewings = [sewing.get_stitch_data() for sewing in self.sewings]
        return sewings

    def update_edge_finder(self):
        edge_points = []
        edge_point_sizes = []
        matrices = []
        layout = []
        for p in self.patterns:
            ps = p.get_geo_points_unique()
            edge_points.append(ps)
            edge_point_sizes.append(len(ps))
            # What this snapshot was taken from, per panel: the offsets the snap
            # reports are indices into these arrays, and a panel that grew an
            # edge - or split one into two - has an array they do not fit.
            layout.append((int(p.global_uuid), outline_sample_counts(p)))
            matrices.append(np.array(p.calc_matrix()))
        edge_points = np.concatenate(edge_points, dtype=np.float32)
        # console.info('edge_point_sizes', edge_point_sizes)
        edge_point_sizes = np.array(edge_point_sizes, dtype=np.int32)
        matrices = np.concatenate(matrices, dtype=np.float32)
        # console.info('matrices', matrices)
        from Qianyi_DP import pattern_helper
        pattern_helper.update_edges(edge_points, edge_point_sizes, matrices)
        self.edge_points = edge_points
        self.edge_point_sizes = np.cumsum(edge_point_sizes)
        self.edge_finder_layout = tuple(layout)

    def clear_edge_finder(self):
        self.edge_points = None
        self.edge_finder_layout = None

    def edge_finder_is_current(self) -> bool:
        """Whether the edge finder's snapshot still describes the panels.

        The snapshot is a flat array of every panel's outline points, and the
        snap's answer is an index into it. An edit that added or removed an edge
        makes those indices describe a shape the panels no longer have, so the
        snapshot is compared against the panels before it is read.
        """
        layout = getattr(self, "edge_finder_layout", None)
        if self.edge_points is None or layout is None or len(layout) != len(self.patterns):
            return False
        for pattern, entry in zip(self.patterns, layout):  # loop: one panel each
            if int(pattern.global_uuid) != entry[0]:
                return False
            try:
                counts = outline_sample_counts(pattern)
            except Exception:
                # A panel that cannot answer for its outline is not one the
                # snapshot can be read against: the finder is rebuilt.
                return False
            if counts != entry[1]:
                return False
        return True

    def find_nearest_point_on_edge(self, query_point):
        if self.edge_points is None:
            self.update_edge_finder()
        from Qianyi_DP import pattern_helper
        res = pattern_helper.find_nearest_edge(query_point)
        # console.info('res', res)
        # console.info('self.edge_point_sizes', self.edge_point_sizes)
        index = res['res_index']
        weight = res['res_weight']
        n = np.searchsorted(self.edge_point_sizes, index, side='left')
        next_index = index + 1
        if self.edge_point_sizes[n] - 1 == index:
            next_index = self.edge_point_sizes[n - 1] if n > 0 else 0
        if self.edge_point_sizes[n] == index:
            n += 1
        pattern_point_offset = 0 if n == 0 else self.edge_point_sizes[n - 1]
        self.edge_point_offset = index - pattern_point_offset

        self.nearest_pattern = n
        # console.info('n', n, self.edge_point_sizes[n])
        # console.info('next_index', next_index)
        self.nearest_point = self.edge_points[index] * (1 - weight) + self.edge_points[next_index] * weight
        self.query_point = query_point
        # console.warning('self.nearest_point', self.nearest_point)

    def get_nearest_point_data(self):
        """Where the snap is: the panel, its edge, the point and the fraction.

        The numbers come from the edge finder's snapshot. A panel edited since
        that snapshot has edges its offsets were never taken over - reading them
        against the edges the panel has now is what raised a KeyError - so the
        snapshot is checked against the panels, and rebuilt from the pointer
        that asked for it when it is out of date.
        """
        if not self.edge_finder_is_current():
            self.clear_edge_finder()
            self.update_edge_finder()
            if self.query_point is not None:
                self.find_nearest_point_on_edge(self.query_point)
        if not 0 <= int(self.nearest_pattern) < len(self.patterns):
            raise ValueError("the snap names a panel that is not in the project")
        pattern: Pattern = self.patterns[self.nearest_pattern]
        # The samples are the ones the snapshot used, taken from the Sketch
        # again if this panel was marked since.
        pattern.ensure_sections()
        samples = [pattern.sample_points[(None, index)]
                   for index in range(len(pattern.edges))]
        point_offsets = []
        count = 0
        for points in samples:  # loop: one run per outline edge
            point_offsets.append(count)
            count += max(len(points) - 1, 0)
        edge_index = np.searchsorted(point_offsets, self.edge_point_offset, side='right') - 1
        if not 0 <= edge_index < len(pattern.edges):
            raise ValueError("the snap does not land on an edge of the panel it names")
        edge = pattern.edges[edge_index]
        edge_points = np.asarray(samples[edge_index], dtype=np.float32)
        point_index = int(self.edge_point_offset - point_offsets[edge_index])
        if point_index >= len(edge_points) - 1:
            raise ValueError("Point index out of range!!!", point_index, len(edge_points))
        point_start = edge_points[point_index]
        pts = edge_points[:point_index + 1]
        length = (np.sum(np.linalg.norm(pts[1:] - pts[:-1], axis=1)) +
                  np.linalg.norm(self.nearest_point - point_start))
        t = length / edge.length
        return pattern, edge, self.nearest_point, t

    def add_pattern(self, sketch=None):
        """Add one panel, taking `sketch` as its geometry or a new one."""
        p = self.patterns.add()
        # Give it its identity before anything names it: the Sketch it takes is
        # owned by this pattern, and that is a uuid reference.
        p.get_temp_data()
        self.refresh_collection_uuid(self.patterns)
        name = f"pattern_{len(self.patterns):03d}"
        p.name = get_unique_name(self.patterns, name)
        # A panel starts with a Sketch of its own; a copy is handed its source's
        # instead, so no Sketch is made and thrown away.
        p.sketch = sketch if sketch is not None else self.add_sketch(owner=p)
        if sketch is not None and sketch.owner is None:
            sketch.owner = p
        return p

    def add_sketch(self, owner=None) -> Sketch:
        """Add one Sketch, optionally owned by a pattern, and return it."""
        sketch = self.sketches.add()
        sketch.get_temp_data()
        self.refresh_collection_uuid(self.sketches)
        sketch.name = f"sketch_{len(self.sketches):03d}"
        sketch.owner = owner
        return sketch

    def remove_impacted_sewings(self):
        """Drop the sewings flagged as impacted; returns how many went.

        An editor deletes an element but flags every sewing that used it, and a
        deleted element leaves its uuid in the in-memory map still pointing at a
        wrapper that now reads a different uuid - so any lookup of it raises.
        Everything that walks all sewings has to run after the sewings that lost
        a line are gone; `mark_geometry_changed` walks them through
        `get_connected_patterns_and_sewings`.
        """
        indexes = [sewing.get_index() for sewing in self.sewings if sewing.impacted]
        for index in sorted(indexes, reverse=True):
            self.sewings.remove(index)
        if indexes:
            self.refresh_collection_uuid(self.sewings)
            self.selected_sewings.clear()
        return len(indexes)

    def remove_patterns(self, patterns_to_delete, expand_groups=True):
        if expand_groups:
            patterns_to_delete = self._expand_pattern_groups(patterns_to_delete)

        selected_patterns_uuid = [p.global_uuid for p in patterns_to_delete]
        del_idx_list = []
        for sw in self.sewings:
            for side in (sw.side1, sw.side2):
                # The panel the side was made on; a side whose panel is gone
                # (or a panel that is going now) takes the seam with it.
                panel = side.pattern
                if panel is None or panel.global_uuid in selected_patterns_uuid:
                    del_idx_list.append(sw.get_index())
                    break

        for i in sorted(del_idx_list, reverse=True):
            self.sewings.remove(i)
        self.selected_sewings.clear()
        self.refresh_collection_uuid(self.sewings)

        del_idx_list = []
        for p in patterns_to_delete:
            if p.global_uuid != -1:
                obj = global_data.get_obj_by_uuid(p.global_uuid, check_uuid=False)
                if hasattr(obj, 'mesh_object') and obj.mesh_object is not None:
                    bpy.data.objects.remove(obj.mesh_object)
                if obj is not None:
                    del_idx_list.append(obj.get_index())
                else:
                    console.error('cannot find pattern', p.global_uuid)
        for i in sorted(del_idx_list, reverse=True):
            self.patterns.remove(i)

        self.refresh_patterns()
        self.remove_orphan_sketches()

    def remove_orphan_sketches(self) -> int:
        """Drop every Sketch no pattern uses and return how many went.

        A Sketch is the geometry of an instance chain, so it lives exactly as
        long as some panel reads it; Blender does not collect an unreferenced
        property group on its own.
        """
        used = {pattern.sketch_uuid for pattern in self.patterns}
        drop = [index for index, sketch in enumerate(self.sketches)  # loop: one check per Sketch
                if sketch.global_uuid not in used]
        for index in sorted(drop, reverse=True):
            self.sketches.remove(index)
        if drop:
            self.refresh_collection_uuid(self.sketches)
        return len(drop)

    def _expand_pattern_groups(self, patterns_to_delete):
        """Deleting one panel of a generator deletes the whole group.

        A generated panel is not a standalone object: its siblings and the
        generator that produced them are one unit, so removing any of them
        removes the unit.
        """
        expanded = list(patterns_to_delete)
        seen = {p.global_uuid for p in expanded}
        generators_to_remove = []
        for pattern in patterns_to_delete:
            generator = generator_of_pattern(self, pattern)
            if generator is None or generator in generators_to_remove:
                continue
            generators_to_remove.append(generator)
            for output in generator.outputs:
                if output.pattern_uuid == -1:
                    continue
                sibling = global_data.get_obj_by_uuid(output.pattern_uuid, check_uuid=False)
                # A copy of a generated panel belongs to the same group.
                for member in sibling.sketch_members() if sibling is not None else ():
                    if member.global_uuid not in seen:
                        expanded.append(member)
                        seen.add(member.global_uuid)

        if generators_to_remove:
            indices = sorted((generator.get_index() for generator in generators_to_remove
                              if generator.get_index() is not None), reverse=True)
            for index in indices:
                if 0 <= index < len(self.generators):
                    self.generators.remove(index)
            refresh_generators(self)
            self.active_generator_index = max(
                0, min(self.active_generator_index, len(self.generators) - 1))
        return expanded

    def refresh_patterns(self):
        self.refresh_collection_uuid(self.patterns)
        for p in self.patterns:
            p.clear_temp_data()
        refresh_generators(self)


define_temp_prop(QianyiProject, "initialized", False)
define_temp_prop(QianyiProject, "edge_points", None)
define_temp_prop(QianyiProject, "edge_point_sizes", None)
define_temp_prop(QianyiProject, "nearest_point", None)
define_temp_prop(QianyiProject, "query_point", None)
define_temp_prop(QianyiProject, "nearest_pattern", None)
define_temp_prop(QianyiProject, "edge_point_offset", None)
define_temp_prop(QianyiProject, "selected_sewing_edge1", None)
define_temp_prop(QianyiProject, "selected_sewing_point1", None)
# The panel the first click was made on. An edge serves its whole instance
# chain, so the edge alone does not say which member a seam is made on.
define_temp_prop(QianyiProject, "selected_sewing_pattern1", None)
define_temp_prop(QianyiProject, "last_sewing_error", "")
# The fan tool's gesture, built one click at a time: the pivot, then the target,
# then the click that opens the angle. It lives on the project because the tool,
# the operator and the drawing code all have to see the same thing, and because
# nothing about it is a modal: the view stays usable between the clicks.
define_temp_prop(QianyiProject, "fan_pivot", None)
define_temp_prop(QianyiProject, "fan_target", None)

register, unregister = register_classes_factory((UuidType, QianyiProject))
