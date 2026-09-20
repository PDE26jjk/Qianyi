from typing import List, Optional, Tuple

from ..utilities.console import console


class DirSection:
    def __init__(self, section, reverse=False):
        self.section: Section = section
        self.reverse: bool = reverse


# Doubly linked list node, --> next in CCW
class Section:
    link_sections: List[List[DirSection]] = []  # [[sec1,sec2,...],[sec3,...],...] sec1 link to sec2 etc.

    def __init__(self, edge, start_pos, end_pos):
        self.start_pos = start_pos
        self.end_pos = end_pos
        from .geometry import Edge2D
        self.edge: Edge2D = edge
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

    def split(self, radio, reverse=False, check_link=True):
        # sections = self.edge.sections
        # index = self.edge.find_section_index(self.start_pos)
        # next_pos = 1. if index == len(sections) - 1 else sections[index + 1].start_pos
        # split_pos = (next_pos - self.start_pos) * radio + self.start_pos
        # new_section = self.edge.add_section(split_pos)
        # if new_section is None:
        #     raise ValueError("new_section is None")
        # return self, new_section
        self.seg = -1  # need to be recalculated.
        length = self.end_pos - self.start_pos
        if not reverse:
            split_pos = self.start_pos + length * radio
            new_sec = Section(self.edge, split_pos, self.end_pos)
            self.end_pos = split_pos
            new_sec.prev = self
            new_sec.next = self.next
            if self.next is not None:
                # Keep the chain doubly linked: the section after this one
                # still points back at it, so a walk the other way would skip
                # the new one.
                self.next.prev = new_sec
            self.next = new_sec
        else:
            split_pos = self.end_pos - length * radio
            new_sec = Section(self.edge, self.start_pos, split_pos)
            self.start_pos = split_pos
            new_sec.next = self
            new_sec.prev = self.prev
            if self.prev is not None:
                self.prev.next = new_sec
            self.prev = new_sec
            if self.edge.section_start is self:
                # The new section holds the beginning of the edge now, so it is
                # the head. `Edge2D.sections()` walks from here while it is not
                # `section_end`, so a head left in the middle of the edge hides
                # every section before it - and those sections never get their
                # mesh points, which is what made one side of a seam stitch half
                # as many times as the other.
                self.edge.section_start = new_sec
        if check_link and self.link_map_id != -1:
            new_link_sections = [DirSection(new_sec, False)]
            new_sec.link_map_id = len(Section.link_sections)
            im_reverse = self.is_reverse() ^ reverse
            for sec in Section.link_sections[self.link_map_id]:
                if sec.section is not self:
                    its_reverse = im_reverse ^ sec.reverse
                    _, its_new_sec = sec.section.split(radio, its_reverse, check_link=False)
                    its_new_sec.link_map_id = new_sec.link_map_id
                    new_link_sections.append(its_new_sec)
            Section.link_sections.append(new_link_sections)
        new_sec.outsize = self.outsize
        return self, new_sec

    def split_pending(self):
        self.seg = -1  # need to be recalculated.
        length = self.end_pos - self.start_pos
        abs_l = self.absolute_length()
        sec = self
        min_r = self.edge.pattern.granularity * 0.02 / abs_l
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
            sec.end_pos = split_pos
            new_sec.next = sec.next
            new_sec.prev = sec
            sec.next = new_sec
            sec = new_sec
            last_r = r

        self.pending_split.clear()

    def is_reverse(self):
        if self.link_map_id == -1:
            return False
        # console.warning("is_reverse", Section.link_sections,self.link_map_id )
        for sec in Section.link_sections[self.link_map_id]:
            if sec.section is self:
                return sec.reverse
        raise ValueError("Section.is_reverse: Something Wrong!!!")

    def link_to(self, other: 'Section', reverse=False):
        if self is other:
            raise ValueError("Sewing overlap!!!")
        # console.warning("link_to", Section.link_sections, self.link_map_id, other.link_map_id)
        if self.link_map_id == -1 or other.link_map_id == -1:
            if self.link_map_id == -1 and other.link_map_id == -1:
                index = len(Section.link_sections)
                other.link_map_id = self.link_map_id = index
                Section.link_sections.append([DirSection(self, False), DirSection(other, reverse)])
            elif self.link_map_id == -1:
                its_reverse = other.is_reverse()
                Section.link_sections[other.link_map_id].append(DirSection(self, its_reverse ^ reverse))
                self.link_map_id = other.link_map_id
            else:
                im_reverse = self.is_reverse()
                Section.link_sections[self.link_map_id].append(DirSection(other, im_reverse ^ reverse))
                other.link_map_id = self.link_map_id
        else:
            if self.link_map_id == other.link_map_id:
                raise ValueError("Sewing overlap!!!")
            link_sections = Section.link_sections[self.link_map_id]
            other_link_sections = Section.link_sections[other.link_map_id]
            all_sections = link_sections + other_link_sections
            im_reverse = self.is_reverse()
            for sec in all_sections:
                sec.section.count = 0
            for sec in all_sections:
                sec.section.count += 1
            for sec in all_sections:
                if sec.section.count > 1:
                    raise ValueError("Sewing overlap!!!")
            reverse ^= im_reverse
            for sec in other_link_sections:
                sec.section.link_map_id = self.link_map_id
                sec.reverse ^= reverse

            Section.link_sections[self.link_map_id].extend(other_link_sections)
            other_link_sections.clear()

    def absolute_length(self):
        return (self.end_pos - self.start_pos) * self.edge.length

    # def __repr__(self):
    #     return f"({self.edge.global_uuid}: {self.start_pos},{self.length},{self.seg})"
