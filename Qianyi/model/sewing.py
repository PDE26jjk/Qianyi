import math
from typing import List

import numpy as np
from bpy.props import EnumProperty, FloatProperty, PointerProperty, IntProperty, CollectionProperty, \
    FloatVectorProperty, BoolProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .internal_line import InternalLine
from ..utilities.console import console
from ..utilities.geometric_operation import split_polyline
from .. import global_data
from .model_data import ModelData, define_temp_prop, Selectable
from .geometry import Edge2D, Section


# LineType = [
#     ("EDGE", "Edge", "", 1),
#     ("INTERNAL_LINE", "InternalLine", "", 2),
# ]

# How many pieces one span's walk may visit before it counts as a loop. A walk
# runs over the pieces of one chain, and no pattern has this many.
MAX_WALK_PIECES = 10000


class SewingSpan(PropertyGroup):
    """One drawn run of a seam side.

    A span is what a seam side used to be before many-to-many: a start place and
    an end place on one chain, plus the direction it was drawn in. A side now
    holds a set of them, so one long edge can be sewn to several short ones.
    """

    line1_uuid: IntProperty(name="line1_id")
    pos1: FloatProperty(name="position1", min=0.0, max=1.0, default=0.0)
    line2_uuid: IntProperty(name="line2_id")
    pos2: FloatProperty(name="position2", min=0.0, max=1.0, default=1.0)
    reverse: BoolProperty(name="reverse", default=False)  # False for ccw, True for not ccw

    def update_data(self, line1, pos1, line2, pos2, reverse):
        self.line1_uuid = line1.global_uuid
        self.pos1 = pos1
        self.line2_uuid = line2.global_uuid
        self.pos2 = pos2
        # The direction is a bool of the seam's own, not of whatever the caller
        # computed it with: a comparison of a numpy length answers a numpy bool,
        # and RNA refuses that where it wants True/False.
        self.reverse = bool(reverse)

    def turn_round(self) -> None:
        """Read this span the other way: the same stretch, walked from its far end.

        The two places are swapped and the direction with them, which is what
        `side_run` reads: a run from A to B going forward is the run from B to A
        going back. The stretch of the chain the span covers and its length stay
        as they were. It is its own inverse.
        """
        self.line1_uuid, self.line2_uuid = self.line2_uuid, self.line1_uuid
        self.pos1, self.pos2 = self.pos2, self.pos1
        self.reverse = not self.reverse

    @property
    def line1(self):
        # During a pattern rebuild the edge collection is rewritten before the
        # sewings are remapped, so this lookup can transiently point at a
        # shifted wrapper. Return None instead of raising.
        return global_data.get_obj_by_uuid(self.line1_uuid, check_uuid=False)

    @property
    def line2(self):
        return global_data.get_obj_by_uuid(self.line2_uuid, check_uuid=False)


class SewingOneSide(PropertyGroup, ModelData, Selectable):
    """One side of a seam: an ordered set of drawn spans on one pattern.

    The spans are kept in the order they were drawn, and they need not be
    geometrically contiguous: each is a run of a chain in its own right, and the
    side's sections are the concatenation of theirs. A side holds at least one
    span once it has been given one; a side with none has nothing to stitch.
    """

    spans: CollectionProperty(type=SewingSpan, name="spans")
    # The pattern this side was made on. An edge is shared by its whole instance
    # chain, so the edge alone cannot say which member a side belongs to: it
    # answers the chain's owner, which is a different pattern as soon as a chain
    # has a copy.
    pattern_uuid: IntProperty(name="pattern_id", default=-1)

    def update_data(self, line1, pos1, line2, pos2, reverse, pattern=None):
        """Make this side the single run it used to be, drawn once."""
        self.spans.clear()
        self.add_span(line1, pos1, line2, pos2, reverse)
        self.pattern_uuid = pattern.global_uuid if pattern is not None else -1

    def add_span(self, line1, pos1, line2, pos2, reverse):
        """Append one drawn run, after the runs already there."""
        span = self.spans.add()
        span.update_data(line1, pos1, line2, pos2, reverse)
        return span

    def clear_spans(self) -> None:
        """Drop every run; the side then has nothing to stitch."""
        self.spans.clear()

    def turn_round(self) -> None:
        """Read this side the other way: reverse the span order and turn each round.

        A side is the runs in the order they were drawn, so reading it backwards
        is reading the last run first - each of them turned round - which is what
        makes the two sides of a seam start at the ends that face each other.
        It is its own inverse.
        """
        # A loop over the side's spans is what this is: each entry is one RNA
        # property write on the collection, which numpy cannot express.
        ordered = list(self.spans)
        runs = [(int(span.line1_uuid), float(span.pos1), int(span.line2_uuid),
                 float(span.pos2), bool(span.reverse)) for span in ordered]
        for span, (line1, pos1, line2, pos2, reverse) in zip(ordered, reversed(runs)):
            span.line1_uuid, span.pos1 = line2, pos2
            span.line2_uuid, span.pos2 = line1, pos1
            span.reverse = not reverse

    @property
    def pattern(self):
        """The pattern this side was made on.

        The record is the side's own: the pattern it was made on, by identity. A
        seam side names its pattern or nothing - it never reaches back into the
        geometry it runs along, because an edge is shared by its whole instance
        chain and answers a different pattern than the one the seam was made on.
        The lookup answers None for a pattern an editor removed, and the seam then
        has no side rather than silently becoming the owner of the edge.
        """
        if self.pattern_uuid == -1:
            return None
        return global_data.get_obj_by_uuid(self.pattern_uuid, check_uuid=False)

    @property
    def sewing(self):
        """The seam this side belongs to, or None.

        A seam records its own two sides when it is updated, so that answer is
        used when it is there; a side that nothing has updated yet - a file just
        opened - is found by walking the project's sewings. Every caller that
        holds a side and needs the seam asks here, and none of them has to know
        which of the two answered.

        What is kept is the seam's identity, not the wrapper the answer came
        from: removing a seam shifts the ones behind it, and a wrapper kept from
        before that reads whichever seam moved into its place. The wrapper is
        re-read from the identity map, which is what makes this answer follow the
        seam the half is in and not its slot.
        """
        remembered = self.sewing_uuid_temp
        if remembered != -1:
            seam = global_data.uuid2obj.get(remembered)
            try:
                if isinstance(seam, Sewing) and seam.global_uuid == remembered:
                    return seam
            except Exception:
                # A removed datablock raises on any read; the walk below is the
                # answer for a seam that is gone.
                pass
            self.sewing_uuid_temp = -1
        for candidate in getattr(self.id_data, "sewings", ()):  # loop: one seam
            for index in range(len(candidate.sides)):  # loop: its two sides
                if candidate.sides[index].global_uuid == self.global_uuid:
                    self.sewing_uuid_temp = candidate.global_uuid
                    return candidate
        return None

    @sewing.setter
    def sewing(self, value):
        self.sewing_uuid_temp = value.global_uuid if value is not None else -1


define_temp_prop(SewingOneSide, "sewing_uuid_temp", -1)


class Sewing(PropertyGroup, ModelData, Selectable):
    sides: CollectionProperty(type=SewingOneSide)
    color: FloatVectorProperty(
        name="color",
        description="The color of the Sewing",
        subtype="COLOR",
        default=(1., 1, 1),
        size=3,
    )

    def get_side1(self):
        if len(self.sides) < 1:
            self.sides.add()
        return self.sides[0]

    def get_side2(self):
        if len(self.sides) < 2:
            if len(self.sides) < 1:
                self.sides.add()
            self.sides.add()
        return self.sides[1]

    @property
    def pattern1(self):
        return self.side1.pattern

    @property
    def pattern2(self):
        return self.side2.pattern

    @property
    def side1(self):
        return self.get_side1()

    @property
    def side2(self):
        return self.get_side2()

    def clear_temp_data(self):
        self.need_render_update = True

    def forget_identity(self) -> None:
        """Drop this seam and both of its sides from the identity map.

        Called while the seam is still in the project, just before it is
        removed: a seam's sides live in the property group that goes with it, so
        the map's entries for them would answer with freed memory afterwards -
        the pick pass holds those uuids and reads them back on the next move over
        the editor. The sides are read from the collection itself, not through
        `side1`/`side2`, which add a side that is missing.
        """
        for side in self.sides:  # loop: one side of this seam per step
            side.forget_uuid()
        self.forget_uuid()

    def update(self):
        if not self.need_render_update:
            return
        # The points are read before the flag is cleared: a side whose spans
        # cannot be walked (`calc_sewing_side_render_points` refuses one that
        # leaves an open chain, say) leaves the mark standing, so the next frame
        # tries again instead of being stuck with a renderer and no batch.
        # One polyline per drawn span, in drawing order.
        render_points1 = calc_sewing_side_render_points(self.side1)
        render_points2 = calc_sewing_side_render_points(self.side2)
        self.need_render_update = False
        if global_data.renderers_enabled and (self.renderer is None
                                              or not self.renderer.bound_to(self)):
            from ..gizmos.sewing_renderer import SewingRenderer
            self.renderer = SewingRenderer(self)
        self.side1.sewing = self
        self.side2.sewing = self
        if global_data.renderers_enabled:
            self.renderer.update_batch_edges(render_points1, render_points2)

    def get_stitch_data(self):
        """This seam's payload entry: its two patterns and its stitch pairs.

        Each side is walked span by span and the two walks are zipped: pair k is
        the k-th vertex of side 1 against the k-th of side 2. The two walks have
        to take the same number of samples - that is what the guard checks - and
        a seam whose walks disagree is reported here rather than zipped into a
        ragged array.
        """
        ss1 = self.side1
        ss2 = self.side2
        # The patterns the sides were made on, not the owners of the edges they
        # run along: those edges serve the whole instance chain.
        pattern1 = ss1.pattern
        pattern2 = ss2.pattern
        for pattern in (pattern1, pattern2):
            if pattern is None:
                raise ValueError(f"sewing {self.name or '(unnamed)'} has no pattern on "
                                 f"one of its sides: it was saved before a side "
                                 f"recorded one, or that pattern was removed")
            if pattern.mesh_object is None:
                # A crossing outline is not meshed at all, so a sewing that
                # ends on it has no vertices to pair. Say that instead of
                # failing on a None object further down.
                raise ValueError(f"pattern {pattern.name or '(unnamed)'} has no mesh "
                                 f"(its outline is invalid?)")
        if pattern1.need_geo_update:
            pattern1.calc_mesh_edge_points()
        if pattern2.need_geo_update:
            pattern2.calc_mesh_edge_points()
        patterns = (pattern1.mesh_object.qmyi_simulation_props.simulation_index,
                    pattern2.mesh_object.qmyi_simulation_props.simulation_index)

        # The sides are paired by the pieces the linking run left: a piece of one
        # side and the piece of the other it was linked to carry the same stretch
        # of the seam, so their samples are paired in order.
        stitches = np.asarray(pair_by_sections(side_pieces(ss1), side_pieces(ss2)),
                              dtype=np.int64)
        # A side that runs outside its pattern has no vertices there, so those
        # pairs cannot be stitched. Dropping the same positions on both sides
        # keeps every remaining stitch paired the way it was.
        inside = (stitches[:, 0] >= 0) & (stitches[:, 1] >= 0)
        if not inside.all():
            # Back to the map's own dtype: the walk uses a signed placeholder,
            # and the engine has always been handed the deduplicated index
            # dtype.
            stitches = stitches[inside].astype(
                pattern1.mesh_edge_index_map.dtype, copy=False)

        return {'patterns': patterns, 'stitches': stitches, 'angle': 0.}


define_temp_prop(Sewing, "need_render_update", True)
define_temp_prop(Sewing, "renderer", None)
define_temp_prop(Sewing, "sections1", list)
define_temp_prop(Sewing, "sections2", list)
define_temp_prop(Sewing, "impacted", False)


def piece_vertices(pattern, piece, count):
    """The mesh vertices the first `count` samples of one piece are.

    A piece outside the pattern holds no vertex: its samples are the placeholder
    -1, which the caller drops. The placeholder has to be signed - the index map
    is unsigned, where -1 would read back as 4294967295 and pass for a vertex.
    """
    if piece.outsize or piece.mesh_start_point < 0:
        return np.full(int(count), -1, dtype=np.int64)
    index_map = pattern.mesh_edge_index_map
    chunk = index_map[piece.mesh_start_point: piece.mesh_start_point + int(count)]
    if int(count) - len(chunk) == 1:
        chunk = np.append(chunk, index_map[0])
    if int(count) != len(chunk):
        raise IndexError("Something went wrong")
    return chunk.astype(np.int64, copy=False)


def side_pieces(side):
    """One side's pieces, in the order it is stitched, with what each one holds.

    Returns a list of ``(piece, samples, head, tail, ends_run, run_index,
    far_first)``: the piece's own vertices in stitching order, the vertex the
    walk enters the piece at and the vertex it leaves it at, whether this is
    where one of the side's drawn runs ends - which is a sample of its own -
    which of the side's runs the piece belongs to, and whether that sample comes
    before the piece's own samples in the stitch order (a run walked backwards
    starts at its far end). The pieces come from each pattern's own copy of the
    section stage, so they are the pieces the linking run cut and paired.
    """
    pattern = side.pattern
    if pattern is None:
        raise ValueError("a sewing side runs on a pattern that is no longer in "
                         "the scene, so it has no pattern to stitch")
    spans = list(side.spans)
    if not spans:
        raise ValueError("a sewing side holds no span, so it has nothing to stitch")
    out = []
    for run_index, span in enumerate(spans):  # loop: one drawn run of this side per step
        start = pattern.boundary_section(span.line1, span.pos1, span.reverse)
        end = pattern.boundary_section(span.line2, span.pos2, span.reverse)
        pieces = walk_pieces(start, end, span.reverse)
        far_end = 0 if span.reverse else len(pieces) - 1
        for position, piece in enumerate(pieces):
            # loop: one piece of that run per step
            seg = max(int(piece.seg), 1)
            samples = piece_vertices(pattern, piece, seg)
            beyond = piece_vertices(pattern, piece, seg + 1)
            up = int(beyond[-1]) if len(beyond) == seg + 1 else -1
            if position == far_end and piece.mesh_end_point != -1:
                # The far end of a walk is read one sample above the piece that
                # ends it; on the piece that wraps the pattern's sample array
                # that read lands on the first sample of the next curve, where
                # the pattern recorded its own first sample instead.
                up = int(pattern.mesh_edge_index_map[piece.mesh_end_point])
            down = int(samples[0]) if len(samples) else -1
            if span.reverse:
                # A reversed walk enters its piece from the top of the chain and
                # leaves at the bottom, and its samples run the other way.
                samples = samples[::-1]
                head, tail = up, down
            else:
                head, tail = down, up
            out.append((piece, samples, head, tail, position == far_end, run_index,
                        bool(span.reverse) and position == far_end))
    return out


def pair_by_sections(first, second):
    """The stitch pairs: the samples of the linked pieces, paired in order.

    Both sides' pieces are the linked pairs the merge left, in the order the seam
    stitches them, so the two lists are walked together: a piece of one side and
    the piece of the other it was linked to cover the same stretch of the seam,
    and their samples are paired from the start of that stretch to its end.
    Nothing is divided and no progress is computed - the correspondence IS the
    linked sections, which is where the proportional cutting already happened.

    A piece a drawn run ends at carries the run's own end as a sample, and it is
    paired with the other side's end of the same piece: that is the point the two
    runs' ends meet. Where one side's two runs meet one point of the other, both
    those samples are paired with it: the end the piece before the boundary
    reached is joined to the point the piece after it begins at, and that piece's
    own first vertex is joined to the same point as it is walked. Where the two
    facing ends are one vertex - the runs meet at it - the pair is made twice and
    is dropped when it stands next to itself, because one vertex meeting one
    vertex is one stitch however many runs brought it there. A loop repeats its
    opening pair at its close, and that one is not next to itself, so it stays.
    """
    if len(first) != len(second):
        raise ValueError(
            f"the two sides have {len(first)} and {len(second)} pieces to stitch, "
            f"so the linking run did not pair them")
    # Each piece's vertices, in the order the seam runs through it, so the walk
    # below pairs them and can reach back across a boundary.
    ours = [piece_run(entry[1], entry[2], entry[3], entry[4], entry[6])
            for entry in first]
    theirs = [piece_run(entry[1], entry[2], entry[3], entry[4], entry[6])
              for entry in second]
    pairs = []
    last = None

    def add(pair) -> None:
        """Keep a pair unless it is the one just made."""
        nonlocal last
        if pair != last:
            pairs.append(pair)
        last = pair

    # Both lists are in the order the seam stitches them - each side's walk runs
    # from the seam's start to its end, whichever way round its chain runs - and
    # the merge cut the two sides into pieces that correspond, so the pieces of
    # one list are the partners of the pieces of the other, in order.
    for index in range(len(ours)):
        if index > 0:
            # The boundary between the two pieces. Where our side's two runs meet
            # there and the other side's fabric runs on through it, the other side
            # has one point at that place and we have two ends: the end the piece
            # before reached is joined to the point the piece after begins at, and
            # that piece's own first vertex is joined to the same point when it is
            # walked. The two runs of one side meeting one point of the other is
            # what the seam is; nothing is left unstitched on either side.
            our_junction = first[index - 1][5] != first[index][5]
            their_junction = second[index - 1][5] != second[index][5]
            if our_junction and not their_junction and len(ours[index - 1]):
                add((int(ours[index - 1][-1]), int(theirs[index][0])))
            elif their_junction and not our_junction and len(theirs[index - 1]):
                add((int(ours[index][0]), int(theirs[index - 1][-1])))
        ours_here, theirs_here = ours[index], theirs[index]
        # The two runs are the same stretch of the seam, from its start to its end
        # and one sample apart, so they pair sample by sample. One of them can be
        # one vertex longer: a run that ends here carries its own end, while the
        # other side's run carries the same place as its next piece's first
        # vertex. That last vertex is what the longer run's own end meets.
        for offset in range(min(len(ours_here), len(theirs_here))):
            add((int(ours_here[offset]), int(theirs_here[offset])))
        if len(ours_here) > len(theirs_here):
            pair = (int(ours_here[-1]), int(second[index][3]))
        elif len(theirs_here) > len(ours_here):
            pair = (int(first[index][3]), int(theirs_here[-1]))
        else:
            pair = None
        if pair is not None:
            add(pair)
    return pairs


def piece_run(samples, head, tail, ends_run, far_first):
    """One piece's vertices, in the order the seam runs through it.

    The piece's own samples, with the vertex at the run's own end added at the
    end - or at the start, when the run is walked backwards, because then the
    walk reaches the run's end first. A piece that does not end a run holds its
    own samples alone: the vertex at either side of it is the sample the piece
    next to it carries.
    """
    if not ends_run:
        return samples
    if far_first:
        return np.concatenate((np.asarray([head], dtype=np.int64), samples))
    return np.concatenate((samples, np.asarray([tail], dtype=np.int64)))


def walk_pieces(start_section, end_section, reverse):
    """The pieces one run visits, in the order the walk visits them.

    A walk stops at `end_section` without visiting it; a run whose two ends are
    the same piece visits that one piece and steps off it, which is how a loop
    or a span inside a single edge is walked.
    """
    pieces = []
    section = start_section
    if section is end_section:
        pieces.append(section)
        section = section.prev if reverse else section.next
    count = 0
    while section is not end_section:
        if section is None:
            raise ValueError("a sewing span runs past the end of its chain")
        pieces.append(section)
        section = section.prev if reverse else section.next
        count += 1
        if count > MAX_WALK_PIECES:
            raise ValueError("sewing side in different pattern!!")
    return pieces


def section_pattern(section):
    """The pattern a piece of a walk belongs to, or None when it is gone.

    A piece is one pattern's own copy of the stage and carries that pattern by
    identity (`section.pattern`), which is why this is the pattern the walk speaks
    about and not the owner of the edges it was cut from.
    """
    return section.pattern


def span_pieces(pattern, span):
    """One span's pieces, with the boundary a walk starts and stops at.

    The boundaries are read from the span's own parameters and cut on this
    pattern's copy (`find_or_add_section`), so a walk of the span has pieces to
    read whichever seam cut them there.
    """
    line1, line2 = span.line1, span.line2
    if line1 is None or line2 is None:
        raise ValueError("a sewing span names an edge that is no longer in the scene")
    reverse = bool(span.reverse)
    sec_start = pattern.find_or_add_section(line1, span.pos1)
    sec_end = pattern.find_or_add_section(line2, span.pos2)
    if sec_start is None:
        raise ValueError(
            f"a sewing span at {span.pos1:.4f} -> {span.pos2:.4f} (reverse={reverse}) "
            f"has no section at its start: the edge it sits on cannot be sewn there")
    if reverse:
        if sec_end is None:
            raise ValueError(
                f"a reversed sewing span cannot end at the far end of an open "
                f"edge (pos1={span.pos1:.4f}, pos2={span.pos2:.4f})")
        sec_start, sec_end = sec_start.prev, sec_end.prev
        if sec_start is None or sec_end is None:
            raise ValueError(
                f"a reversed sewing span at {span.pos1:.4f} -> {span.pos2:.4f} runs "
                f"past the start of its edge: pos1 has to be the far end")
    return sec_start, sec_end, walk_pieces(sec_start, sec_end, reverse)


def calc_sewing_side_sections(ss, sections_start_end):
    """Every piece of one side: its spans' pieces, concatenated in drawing order.

    A side is a set of runs now, so this walks each span the way a whole side
    used to be walked and hands both consumers - the proportional merge and the
    stitch walk - one list per side. `sections_start_end` is left holding one
    boundary pair per span, which is what the editor and the diagnostics read.
    """
    sections: List[Section] = []
    pattern = ss.pattern
    if pattern is None:
        raise ValueError("a sewing side has no pattern: it was saved before a side "
                         "recorded one, or that pattern was removed")
    spans = list(ss.spans)
    if not spans:
        raise ValueError("a sewing side holds no span, so there is nothing to sew")
    boundaries = []
    directions = []
    for span in spans:  # loop: one drawn run of this side per step
        sec_start, sec_end, pieces = span_pieces(pattern, span)
        boundaries.append((sec_start, sec_end))
        sections.extend(pieces)
        directions.extend([bool(span.reverse)] * len(pieces))
    sections_start_end.clear()
    sections_start_end.extend(boundaries)

    lengths = np.fromiter((obj.absolute_length() for obj in sections), dtype=np.float64)
    scans = np.cumsum(lengths)
    if scans[-1] <= 0:
        raise ValueError(
            f"a sewing side of {len(spans)} span(s) covers no length, "
            f"so there is nothing to sew")
    lengths /= scans[-1]
    scans /= scans[-1]

    return sections, lengths, scans, directions


# Create sections and calculate intersections before call it.
def calc_sewing_sections(sewings):
    link_sections = Section.link_sections
    # Start a new linking run: the ids in the table are only meaningful for the
    # run that wrote them, and the sections on this run's sides are the ones
    # that are about to be registered.
    Section.link_run += 1
    link_sections.clear()

    for sewing in sewings:
        check_sewing_sides(sewing)

    try:
        link_sewings(sewings, link_sections)
    except Exception:
        # A run that failed halfway left a table that describes only part of
        # the alignment: the sections in it would take part in later splits as
        # if their partners were in step. Drop it and move the run on so those
        # sections count as unlinked until a run completes.
        link_sections.clear()
        Section.link_run += 1
        raise

    # The recorded pair is what the editor and diagnostics read; the stitch
    # walk looks the boundaries up again from the sewing's parameters. Refresh
    # it here so the two agree after every cut the merge made.
    for sewing in sewings:
        for side, holder in ((sewing.side1, sewing.sections1),
            (sewing.side2, sewing.sections2)):
            try:
                pattern = side.pattern
                if pattern is None:
                    continue
                holder.clear()
                for span in side.spans:  # loop: one drawn run of this side per step
                    holder.append(
                        (pattern.boundary_section(span.line1, span.pos1, span.reverse),
                         pattern.boundary_section(span.line2, span.pos2, span.reverse)))
            except ValueError as error:
                console.warning(f"sewing {sewing.name or '(unnamed)'}: {error}")


def check_sewing_sides(sewing):
    """Refuse a seam whose sides cannot be resolved, naming the seam.

    A span's `line1` answers None while a pattern is being rebuilt, and the
    sections lookups further down would raise an AttributeError without saying
    which seam or which side was at fault.
    """
    for label in ("side1", "side2"):
        side = getattr(sewing, label)
        for index, span in enumerate(side.spans):  # loop: one drawn run per step
            for field in ("line1", "line2"):
                if getattr(span, field) is None:
                    raise ValueError(
                        f"sewing {sewing.name or '(unnamed)'}: {label} span {index} "
                        f"{field} points at no edge (the pattern it was sewn onto "
                        f"was rebuilt)")


def link_sewings(sewings, link_sections):
    """Split and link the sections of every side of every seam."""
    # Split and link sections by sewings.
    for sewing in sewings:
        ss1, ss2 = sewing.side1, sewing.side2
        if not len(ss1.spans) or not len(ss2.spans):
            # A side whose drawn runs were all dropped has nothing to link. The
            # guard reports it as incomplete; there is no boundary to place.
            continue
        sections1, lengths1, scans1, dirs1 = calc_sewing_side_sections(ss1, sewing.sections1)
        sections2, lengths2, scans2, dirs2 = calc_sewing_side_sections(ss2, sewing.sections2)
        i = j = 0
        n1, n2 = len(sections1), len(sections2)
        # The merge aligns the two sides by normalized progress, so a seam that
        # stretches one edge onto a much longer one still cuts at matching
        # fractions. `tolerance` is how far apart two boundaries may be before
        # they count as different - one mesh step on the shorter side, in
        # fractions, instead of the fixed 5% of the range that used to be here
        # (5% is 1 mm on a 20 mm seam and 100 mm on a 2 m one).
        total1 = sum(section.absolute_length() for section in sections1)
        total2 = sum(section.absolute_length() for section in sections2)
        granularity = min(ss1.pattern.granularity, ss2.pattern.granularity)
        shortest = min(total1, total2)
        if shortest <= 0:
            raise ValueError(
                f"sewing {sewing.name or '(unnamed)'}: one side covers no length")
        # One mesh step on the shorter side, in fractions, with a ceiling: a
        # seam shorter than a mesh step would otherwise get a tolerance above 1,
        # which makes every boundary "close" and hides real mismatches.
        tolerance = min(0.1, granularity / shortest)
        while i < n1 and j < n2:
            # Boundaries closer than `tolerance` count as the same one, but only
            # when linking them swallows no further boundary: the two pieces
            # would otherwise cover different progress and the rest of the merge
            # would stay one piece behind, leaving pieces unlinked (their `seg`
            # stays -1 and the two sides end up with different stitch counts).
            close = abs(float(scans1[i]) - float(scans2[j])) <= tolerance
            if close:
                if float(scans1[i]) < float(scans2[j]):
                    close = i + 1 >= n1 or float(scans1[i + 1]) > float(scans2[j])
                else:
                    close = j + 1 >= n2 or float(scans2[j + 1]) > float(scans1[i])
            if close:
                sections1[i].link_to(sections2[j], dirs1[i] ^ dirs2[j])
                i += 1
                j += 1
                continue
            if scans1[i] <= scans2[j]:
                cut_length = scans1[i] - (scans2[j] - lengths2[j])
                if cut_length <= 0 or cut_length >= lengths2[j]:
                    # Rounding left the two pieces starting on top of each
                    # other, or the boundary is already this piece's far end:
                    # pair them and carry on rather than writing an empty piece
                    # (a zero-length piece makes the sampler divide by zero, and
                    # the stitch walks count it as one more sample).
                    sections1[i].link_to(sections2[j], dirs1[i] ^ dirs2[j])
                    i += 1
                    j += 1
                    continue
                radio = cut_length / lengths2[j]
                head, tail = sections2[j].split(radio, dirs2[j])
                # A walk starts on the low half going forward and on the high
                # half going back; the other half is what it still has to
                # cover.
                leading, continuation = ((head, tail) if not dirs2[j]
                                         else (tail, head))
                sections1[i].link_to(leading, dirs1[i] ^ dirs2[j])
                sections2[j] = continuation
                lengths2[j] -= cut_length
                i += 1
            else:
                cut_length = scans2[j] - (scans1[i] - lengths1[i])
                if cut_length <= 0 or cut_length >= lengths1[i]:
                    sections1[i].link_to(sections2[j], dirs1[i] ^ dirs2[j])
                    i += 1
                    j += 1
                    continue
                radio = cut_length / lengths1[i]
                head, tail = sections1[i].split(radio, dirs1[i])
                leading, continuation = ((head, tail) if not dirs1[i]
                                         else (tail, head))
                sections2[j].link_to(leading, dirs1[i] ^ dirs2[j])
                sections1[i] = continuation
                lengths1[i] -= cut_length
                j += 1

    # Linked sections should have same segments.
    for i, dir_sections in enumerate(link_sections):
        if not dir_sections:
            continue
        # A piece whose edge an editor replaced is left over from a pattern copy
        # that was never rebuilt; its edge and its pattern resolve to None and the
        # piece is skipped rather than touched.
        sections = [entry.section for entry in dir_sections
                    if entry.section.edge is not None
                    and section_pattern(entry.section) is not None]
        if not sections:
            continue
        max_seg = -1
        for sec in sections:
            granularity = section_pattern(sec).granularity
            seg = max(math.ceil(sec.absolute_length() / granularity), 1)
            max_seg = max(max_seg, seg)
        for sec in sections:
            if sec.seg != max_seg:
                sec.seg = max_seg
                sec.edge.need_update_points = True
                # The pieces are one pattern's own copy, so it is that pattern whose
                # samples and mesh have to follow; the edge answers with the
                # owner of the whole chain instead.
                section_pattern(sec).need_geo_update = True
        # console.warning(i, sections, max_seg)


def calc_sewing_span_edges_index(span, parent):
    e1_index = e2_index = -1
    for i, e in enumerate(parent.edges):
        if e.global_uuid == span.line1_uuid:
            e1_index = i
        if e.global_uuid == span.line2_uuid:
            e2_index = i
        if e1_index != -1 and e2_index != -1:
            break
    if e1_index == -1 or e2_index == -1:
        raise ValueError("sewing side in different pattern!!")
    return e1_index, e2_index


def calc_sewing_span_edges(span):
    """The edges of the chain one span of a sewing runs along, in its order.

    A closed chain - a pattern's outline, or an internal line drawn as a loop - is
    a ring: the walk steps over its ends, and a span may wrap all the way round it
    (the `crazy_loop` case below). An open internal line has two ends, so a side
    that would have to leave the chain is refused here instead of wrapping onto
    the other end of the line.
    """
    parent = span.line1.get_parent()
    chain_edges = parent.edges
    e1_i, e2_i = calc_sewing_span_edges_index(span, parent)
    closed = bool(getattr(parent, "is_loop", True))
    e_i = e1_i
    edges: List[Edge2D] = [chain_edges[e_i]]
    crazy_loop = e1_i == e2_i and (span.pos1 > span.pos2) ^ span.reverse
    step = -1 if span.reverse else 1
    if crazy_loop and not closed:
        raise ValueError("a sewing side cannot wrap an open internal line")
    if crazy_loop:
        e_i = (e_i + step) % len(chain_edges)
        edges.append(chain_edges[e1_i])
    while e_i != e2_i:
        if not closed and not 0 <= e_i + step < len(chain_edges):
            raise ValueError("a sewing side runs past the end of an internal line")
        e_i = (e_i + step) % len(chain_edges)
        edges.append(chain_edges[e_i])
    return edges


def calc_sewing_span_render_points(span):
    """One span's own polyline, the way it is drawn."""
    edges = calc_sewing_span_edges(span)
    # console.info(edges)

    if len(edges) == 1:
        pos1, pos2 = span.pos1, span.pos2
        if pos1 > pos2:
            pos1, pos2 = pos2, pos1
        new_percent = (pos2 - pos1) / (1.0 - pos1)
        _, render_points = split_polyline(edges[0].render_points, pos1)
        render_points, _ = split_polyline(render_points, new_percent)
        render_points = render_points.astype(np.float32)
        # console.info(render_points)
    else:
        if not span.reverse:
            _, start_chain = split_polyline(edges[0].render_points, span.pos1)
            end_chain, _ = split_polyline(edges[-1].render_points, span.pos2)
        else:
            start_chain, _ = split_polyline(edges[0].render_points, span.pos1)
            _, end_chain = split_polyline(edges[-1].render_points, span.pos2)

        render_points = [start_chain]
        for i in range(1, len(edges) - 1):
            render_points.append(edges[i].render_points)
        render_points.append(end_chain)
        if span.reverse:
            render_points = render_points[::-1]
        render_points = np.concatenate(render_points, dtype=np.float32)
    if span.reverse:
        render_points = np.flip(render_points, axis=0)
    return np.ascontiguousarray(render_points)


def calc_sewing_side_render_points(side):
    """One polyline per drawn span of a side, in the order it was drawn.

    The renderer draws every one of them; a side drawn as several runs is
    several polylines, and they are never joined into one - the runs are not
    contiguous and a joined polyline would draw a line across the pattern.
    """
    return [calc_sewing_span_render_points(span) for span in side.spans]


register, unregister = register_classes_factory((SewingSpan, SewingOneSide, Sewing))
