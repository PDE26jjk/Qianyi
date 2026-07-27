from typing import List

from mathutils import Vector

from ...utilities.coords_transform import region2view_coord, view2region_coord
from ...gizmos.moving_curve import TempPoint
from ...gizmos.moving_curve import MovingCurve
from ...utilities.console import console_print, console
from .IState import IState, StateResultType


def is_valid_dist(context, v0, v1):
    v0 = view2region_coord(context, v0)
    v1 = view2region_coord(context, v1)
    # console_print("v0", v0, "v1", v1, "dis_sq", (v0[0] - v1[0]) ** 2 + (v0[1] - v1[1]) ** 2)
    return (v0[0] - v1[0]) ** 2 + (v0[1] - v1[1]) ** 2 > 49


class CurvePenState(IState):

    @property
    def state_id(self):
        return "draw curve by pen"

    def __init__(self):
        super().__init__()
        self.point_position = (-1, -1)
        self.event = None
        self.moving_curves: List[MovingCurve] = []
        self.lmb_pressed = False
        self.circle = False

    def handle_event(self, context, event, operator):
        self.event = event
        if event.type == "TIMER":
            return StateResultType.CONTINUE
        pos = region2view_coord(context, (event.mouse_region_x, event.mouse_region_y))
        # console.warning(event.type, event.value)
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self.lmb_pressed = True
            if self.circle:
                console.info("end click")
                return StateResultType.SUCCESS
            if len(self.moving_curves) == 0:
                mc = MovingCurve()
                mc.vertex0.co = mc.vertex1.co = pos[:]
                self.moving_curves.append(mc)
            else:
                mc = self.moving_curves[-1]
                if is_valid_dist(context, mc.vertex0.co, pos):
                    mc = MovingCurve()
                    mc.vertex0.co = mc.vertex1.co = pos[:]
                    self.moving_curves.append(mc)
                    console.info("new mc")
                else:
                    console.info("end click")
                    if len(self.moving_curves) >= 2:
                        del self.moving_curves[-1]
                        return StateResultType.SUCCESS

        elif event.type == 'MOUSEMOVE':
            self.circle = False
            if self.moving_curves:
                mc = self.moving_curves[-1]
                mc.handle2_type = "VECTOR"
                if is_valid_dist(context, mc.vertex0.co, pos):
                    mc.vertex1.co = pos[:]
                    if self.lmb_pressed:
                        mc.handle1_type = "ALIGNED"
                        mc.handle1.co = pos[:]
                        if len(self.moving_curves) >= 2:
                            mc = self.moving_curves[-2]
                            mc.handle2_type = "ALIGNED"
                            # symmetry
                            mc.handle2.co = 2 * Vector(mc.vertex1.co) - Vector(pos[:])
                    elif (len(self.moving_curves) >= 2 and
                          (not is_valid_dist(context, self.moving_curves[0].vertex0.co, pos))):
                        # console.info("cycle")
                        # cycle
                        self.circle = True
                        first_mc = self.moving_curves[0]
                        mc.vertex1.co = first_mc.vertex0.co
                        if first_mc.handle1_type == "ALIGNED":
                            mc.handle2_type = "ALIGNED"
                            mc.handle2.co = 2 * Vector(mc.vertex1.co) - Vector(first_mc.handle1.co)
                else:
                    mc.vertex1.co = mc.vertex0.co
                    if self.lmb_pressed:
                        mc.handle1_type = "VECTOR"
                        mc.handle1.co = mc.vertex0.co
                        if len(self.moving_curves) >= 2:
                            mc = self.moving_curves[-2]
                            mc.handle2_type = "VECTOR"
                            mc.handle2.co = mc.vertex1.co

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.lmb_pressed = False

        elif event.type == 'RET' and event.value == 'PRESS':
            if len(self.moving_curves) >= 2:
                del self.moving_curves[-1]
                return StateResultType.SUCCESS
        elif event.type == 'BACK_SPACE' and event.value == 'PRESS':
            if self.moving_curves:
                mc = self.moving_curves[-1]
                if mc.handle1_type != "VECTOR":
                    mc.handle1_type = "VECTOR"
                else:
                    del self.moving_curves[-1]
                    if not self.moving_curves:
                        return StateResultType.FAILURE
                    else:
                        self.moving_curves[-1].vertex1.co = pos[:]
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            return StateResultType.FAILURE
        self.point_position = pos
        self.on_data_change(context)
        return StateResultType.CONTINUE
