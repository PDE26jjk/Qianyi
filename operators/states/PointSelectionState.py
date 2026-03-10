from utilities.console import console_print
from .IState import IState, StateResultType


class MouseOperator:
    PRESS = 'PRESS'
    RELEASE = 'RELEASE'


class PointPickState(IState):

    @property
    def state_id(self):
        return "pick a point"

    def __init__(self, success_operator=MouseOperator.PRESS):
        super().__init__()
        self.point_position = (0, 0)
        self.event = None
        self.success_operator = success_operator

    def handle_event(self, context, event, operator):
        self.event = event
        if event.type == 'MOUSEMOVE':
            # context.workspace.status_text_set(f"MOUSEMOVE {(event.mouse_region_x, event.mouse_region_y)}")
            self.point_position = (event.mouse_region_x, event.mouse_region_y)
            self.on_data_change(context)
            return StateResultType.CONTINUE
        elif event.type == 'LEFTMOUSE' and event.value == self.success_operator:
            self.point_position = (event.mouse_region_x, event.mouse_region_y)
            self.on_data_change(context)
            return StateResultType.SUCCESS
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            return StateResultType.FAILURE

        return StateResultType.CONTINUE
