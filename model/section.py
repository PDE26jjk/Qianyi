from typing import List, Optional, Tuple


class DirSection:
    def __init__(self, section, reverse=False):
        self.section: Section = section
        self.reverse: bool = reverse


# Doubly linked list node, -> next in CCW
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
        # self.length = 0.
        self.link_map_id = -1

    def split(self, radio, reverse=False, check_link=True):
        # sections = self.edge.sections
        # index = self.edge.find_section_index(self.start_pos)
        # next_pos = 1. if index == len(sections) - 1 else sections[index + 1].start_pos
        # split_pos = (next_pos - self.start_pos) * radio + self.start_pos
        # new_section = self.edge.add_section(split_pos)
        # if new_section is None:
        #     raise ValueError("new_section is None")
        # return self, new_section
        length = self.end_pos - self.start_pos
        if not reverse:
            split_pos = self.start_pos + length * radio
            new_sec = Section(self.edge, split_pos, self.end_pos)
            self.end_pos = split_pos
            new_sec.prev = self
            new_sec.next = self.next
            self.next = new_sec
        else:
            split_pos = self.end_pos - length * radio
            new_sec = Section(self.edge, self.start_pos, split_pos)
            self.start_pos = split_pos
            new_sec.next = self
            new_sec.prev = self.prev
            self.prev = new_sec
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

        return self, new_sec

    def is_reverse(self):
        if self.link_map_id == -1:
            return False
        for sec in Section.link_sections[self.link_map_id]:
            if sec.section is self:
                return sec.reverse
        raise ValueError("Section.is_reverse: Something Wrong!!!")

    def link_to(self, other: 'Section', reverse=False):
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
