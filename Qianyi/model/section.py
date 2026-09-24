from typing import List, Optional, Tuple

from .. import global_data
from ..utilities.console import console


class DirSection:
    def __init__(self, section, reverse=False):
        self.section: Section = section
        self.reverse: bool = reverse


class SectionRaw:
    """One piece of a chain as the Sketch holds it: a span, and nothing sampled.

    The first stage is topology: which piece of which edge runs from one place on
    it to another, whether a crossing left it outside the outline, and the links
    that make a walk along the chain cheap. A raw piece carries no segment count,
    no sample offset and no mesh offset, because those belong to the panel that
    samples it and a panel must not write to a piece it shares with its copies.
    A panel clones a raw chain into `Section` objects of its own
    (`Section.from_raw`), and every sampled field lives there.
    """

    def __init__(self, edge, start_pos, end_pos):
        self.start_pos = start_pos
        self.end_pos = end_pos
        # The edge is carried by identity and not by reference: an edit that
        # replaces an edge - a divide, a corner merge - leaves the copies of the
        # panels that were not rebuilt holding the wrapper they were cut from,
        # and that wrapper can by then name a different edge. `edge` resolves
        # the identity the way every other cross-reference in the model does.
        self.edge_uuid = edge.global_uuid
        self.prev: Optional['SectionRaw'] = None
        self.next: Optional['SectionRaw'] = None
        self.io_state = 0            # 0 none, 1 leaves the outline, 2 enters it
        self.outsize = False         # a piece of a line outside the outline

    @property
    def edge(self):
        """The edge this span is on, or None when it has been replaced."""
        return global_data.get_obj_by_uuid(self.edge_uuid, check_uuid=False)

    def absolute_length(self):
        """How long this span is on its edge, in millimetres."""
        edge = self.edge
        if edge is None:
            raise ValueError("this span names an edge that is no longer in the "
                             "scene, so its length cannot be measured")
        return (self.end_pos - self.start_pos) * (edge.length or 0.0)

    def __repr__(self):
        return (f"SectionRaw(edge={self.edge.get_index() if self.edge else None}, "
                f"{self.start_pos:.3f}-{self.end_pos:.3f}, outsize={self.outsize})")


# Doubly linked list node, --> next in CCW
class Section:
    link_sections: List[List[DirSection]] = []  # [[sec1,sec2,...],[sec3,...],...] sec1 link to sec2 etc.
    # Bumped by every linking run. `link_map_id` is only an index into
    # `link_sections`, and that table is rebuilt per run, so without this a
    # section linked in an earlier run would read whatever group happens to sit
    # at that index now - another component's pieces, or nothing at all.
    link_run = 0

    def __init__(self, edge, start_pos, end_pos):
        self.start_pos = start_pos
        self.end_pos = end_pos
        # The edge is carried by identity; see `SectionRaw.edge`.
        self.edge_uuid = edge.global_uuid
        self.prev: Optional[Section] = None
        self.next: Optional[Section] = None
        self.seg = -1
        self.start_point = -1
        self.mesh_start_point = -1
        self.mesh_end_point = -1  # only use in last section of loop
        # self.length = 0.
        self.link_map_id = -1
        self.pending_split: List[Tuple[float, int]] = []  # (t,state)
        self.io_state = 0
        self.outsize = False  # outsize of pattern
        self.continuous = False
        # Where this piece sits in the panel that owns it: (the outline's None or
        # an internal line's index, the edge's index). The Sketch's raw stage has
        # no use for it; a panel's copy is found again by it.
        self.edge_key = None
        # The panel this piece belongs to, when it is a panel's own copy: a split
        # tells it about the piece it produced, so the panel's per-edge list and
        # its samples stay in step with the chain.
        self.panel_uuid = -1

    @property
    def edge(self):
        """The edge this piece was cut from, or None when it has been replaced."""
        return global_data.get_obj_by_uuid(self.edge_uuid, check_uuid=False)

    @property
    def panel(self):
        """The panel whose copy this piece is, or None when it is gone."""
        if self.panel_uuid == -1:
            return None
        return global_data.get_obj_by_uuid(self.panel_uuid, check_uuid=False)

    @panel.setter
    def panel(self, value):
        self.panel_uuid = value.global_uuid if value is not None else -1

    @classmethod
    def from_raw(cls, raw) -> 'Section':
        """A panel's own piece, cloned from one of the Sketch's raw spans.

        Only the span and the crossing marks come across: the segment count and
        the sample and mesh offsets are the sampling pass's, and start at their
        unset values on a fresh clone.
        """
        section = cls(raw.edge, raw.start_pos, raw.end_pos)
        section.io_state = raw.io_state
        section.outsize = raw.outsize
        return section

    def split(self, radio, reverse=False, check_link=True):
        """Cut this section in two and return `(the lower half, the upper half)`
        in chain order.

        `self` is always the lower half and always keeps its `start_pos`; only
        its end moves. That is the whole point: the two places that store an
        edge's head (`edge.section_start`, and the previous edge's
        `section_end`) can never go stale, because the head piece is never
        replaced.

        `radio` says where the cut is, measured from the end a walk of this side
        starts at: from `start_pos` when `reverse` is False, from `end_pos` when
        it is True. Which half a caller wants is the caller's business - a walk
        starts on the lower half going forward and on the upper half going
        back, so the direction decides which of the two it takes.
        """
        self.seg = -1  # need to be recalculated.
        length = self.end_pos - self.start_pos
        cut = length * radio
        split_pos = self.end_pos - cut if reverse else self.start_pos + cut
        new_sec = Section(self.edge, split_pos, self.end_pos)
        new_sec.edge_key = self.edge_key
        new_sec.panel = self.panel
        self.end_pos = split_pos
        # One splice for both directions: the new piece takes over the upper
        # half, this one keeps the lower half.
        new_sec.prev = self
        new_sec.next = self.next
        if self.next is not None:
            # Keep the chain doubly linked: the section after the new one still
            # points at this piece, so a walk the other way would skip it.
            self.next.prev = new_sec
        self.next = new_sec
        group = self.linked_group() if check_link else None
        if group is not None:
            new_sec.link_map_id = len(Section.link_sections)
            new_sec.link_run = Section.link_run
            new_link_sections = [DirSection(new_sec, False)]
            im_self_reverse = self.is_reverse()
            im_reverse = im_self_reverse ^ reverse
            for sec in group:
                if sec.section is not self:
                    its_reverse = im_reverse ^ sec.reverse
                    head, tail = sec.section.split(radio, its_reverse, check_link=False)
                    # A partner running the other way along the seam has its
                    # halves swapped relative to this one, so which half goes
                    # where is decided by the relative direction: this group
                    # keeps the halves that match `self`, the new group takes
                    # the halves that match `new_sec`.
                    opposite = sec.reverse ^ im_self_reverse
                    its_kept_sec = tail if opposite else head
                    its_new_sec = head if opposite else tail
                    sec.section = its_kept_sec
                    its_new_sec.link_map_id = new_sec.link_map_id
                    its_new_sec.link_run = Section.link_run
                    new_link_sections.append(DirSection(its_new_sec, opposite))
            Section.link_sections.append(new_link_sections)
        new_sec.outsize = self.outsize
        new_sec.io_state = self.io_state
        if self.panel is not None:
            self.panel.register_piece(new_sec)
        return self, new_sec

    def split_pending(self, min_ratio=None):
        """Apply the cuts recorded in `pending_split`.

        `min_ratio` is how close to the piece before it a cut has to be before
        the two count as the same crossing. Left out, the value comes from the
        panel this piece belongs to (a fraction of its granularity); a caller
        that works on the authored geometry, which has no granularity, passes
        its own.
        """
        self.seg = -1  # need to be recalculated.
        length = self.end_pos - self.start_pos
        abs_l = self.absolute_length()
        sec = self
        if min_ratio is None:
            if self.panel is None:
                raise ValueError(
                    "a cut needs the panel this piece belongs to before it can "
                    "measure itself against a granularity")
            min_ratio = self.panel.granularity * 0.02 / abs_l
        min_r = min_ratio
        last_r = 0
        end_pos = self.end_pos
        start_pos = self.start_pos
        for r, state in self.pending_split:
            # state: 1 out, 2 in
            # console.info(r, state)
            if r - last_r < min_r:
                if state != 0:
                    sec.io_state = state
                continue

            split_pos = start_pos + length * r
            new_sec = Section(self.edge, split_pos, end_pos)
            new_sec.io_state = state
            new_sec.outsize = sec.outsize
            sec.end_pos = split_pos
            new_sec.next = sec.next
            new_sec.prev = sec
            if new_sec.next is not None:
                # Same rule as `split`: the section after the new one used to
                # point at the piece we just cut, so a walk the other way
                # (a reversed seam, or `calc_sewing_side_sections`) would skip
                # the new piece.
                new_sec.next.prev = new_sec
            sec.next = new_sec
            sec = new_sec
            last_r = r

        self.pending_split.clear()

    def is_reverse(self):
        group = self.linked_group()
        if group is None:
            return False
        for entry in group:
            if entry.section is self:
                return entry.reverse
        raise ValueError("Section.is_reverse: Something Wrong!!!")

    def linked_group(self):
        """The group this section belongs to in the current linking run.

        Linking happens per run (`calc_sewing_sections` clears the table and
        fills it again), so an id that survives from an older run says nothing
        about the sections in memory now. Such a section counts as unlinked and
        is re-linked by the run that needs it.
        """
        if self.link_map_id == -1 or self.link_run != Section.link_run:
            return None
        if not 0 <= self.link_map_id < len(Section.link_sections):
            return None
        return Section.link_sections[self.link_map_id]

    def link_to(self, other: 'Section', reverse=False):
        if self is other:
            raise ValueError("Sewing overlap!!!")
        mine = self.linked_group()
        theirs = other.linked_group()
        if mine is None or theirs is None:
            if mine is None and theirs is None:
                index = len(Section.link_sections)
                Section.link_sections.append([DirSection(self, False), DirSection(other, reverse)])
                other.link_map_id = self.link_map_id = index
            elif mine is None:
                its_reverse = other.is_reverse()
                theirs.append(DirSection(self, its_reverse ^ reverse))
                self.link_map_id = other.link_map_id
            else:
                im_reverse = self.is_reverse()
                mine.append(DirSection(other, im_reverse ^ reverse))
                other.link_map_id = self.link_map_id
            self.link_run = other.link_run = Section.link_run
        else:
            if mine is theirs:
                raise ValueError("Sewing overlap!!!")
            all_sections = mine + theirs
            im_reverse = self.is_reverse()
            for sec in all_sections:
                sec.section.count = 0
            for sec in all_sections:
                sec.section.count += 1
            for sec in all_sections:
                if sec.section.count > 1:
                    raise ValueError("Sewing overlap!!!")
            reverse ^= im_reverse
            for sec in theirs:
                sec.section.link_map_id = self.link_map_id
                sec.section.link_run = Section.link_run
                sec.reverse ^= reverse

            mine.extend(theirs)
            theirs.clear()

    def absolute_length(self):
        edge = self.edge
        if edge is None:
            raise ValueError("this piece names an edge that is no longer in the "
                             "scene, so its length cannot be measured")
        return (self.end_pos - self.start_pos) * edge.length

    # def __repr__(self):
    #     return f"({self.edge.global_uuid}: {self.start_pos},{self.length},{self.seg})"
