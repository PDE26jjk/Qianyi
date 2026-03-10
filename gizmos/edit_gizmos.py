from mathutils import Vector


class Point:
    def __init__(self):
        self.pos = Vector((0, 0))


class Line:
    def __init__(self):
        self.type = "Line"
        self.p1 = Vector((0, 0))
        self.p2 = Vector((0, 0))
        self.c1 = Vector((0, 0))
        self.c2 = Vector((0, 0))

    def set_points(self, p1, p2):
        self.p1.x = p1[0]
        self.p1.y = p1[1]
        self.p2.x = p2[0]
        self.p2.y = p2[1]


class Rect:

    def __init__(self, manager):
        self.manager = manager
        self.p1 = Vector((0, 0))
        self.p2 = Vector((0, 0))
        self.l1 = manager.add_line()
        self.l2 = manager.add_line()
        self.l3 = manager.add_line()
        self.l4 = manager.add_line()
        self.update()

    def set_p1(self, point):
        self.p1.x = point[0]
        self.p1.y = point[1]
        self.update()

    def set_p2(self, point):
        self.p2.x = point[0]
        self.p2.y = point[1]
        self.update()

    def update(self):
        self.l1.set_points((self.p1.x, self.p1.y), (self.p2.x, self.p1.y))
        self.l2.set_points((self.p2.x, self.p1.y), (self.p2.x, self.p2.y))
        self.l3.set_points((self.p2.x, self.p2.y), (self.p1.x, self.p2.y))
        self.l4.set_points((self.p1.x, self.p1.y), (self.p1.x, self.p2.y))

    def remove(self):
        self.manager.lines.remove(self.l1)
        self.manager.lines.remove(self.l2)
        self.manager.lines.remove(self.l3)
        self.manager.lines.remove(self.l4)
