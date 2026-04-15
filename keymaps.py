import bpy

from .declarations import Macros, Operators, WorkSpaceTools

constraint_access = (

)

tool_access = (
    *constraint_access,
)

use_construction = (

)

tool_use_select = (

)
tool_base_keymap = (
    (
        Operators.PatternMove2D,
        {"type": "G", "value": "PRESS"},
        None,
    ),
    (
        Operators.EdgeElementsMove2D,
        {"type": "G", "value": "PRESS"},
        None,
    ),
    (
        Operators.ElementsDelete2D,
        {"type": "X", "value": "PRESS"},
        None,
    ),
)

tool_generic = (
    *tool_base_keymap,
    *tool_use_select,
    *tool_access,
)

tool_select = (
    *tool_base_keymap,
    *tool_access,
    (
        Operators.ContextMenu,
        {"type": "RIGHTMOUSE", "value": "PRESS"},
        {"properties": [("delayed", False)]},
    ),
    (
        Operators.Select,
        {"type": "LEFTMOUSE", "value": "CLICK", "any": True},
        None,
    ),
    (
        Operators.Select,
        {"type": "LEFTMOUSE", "value": "CLICK", "shift": True},
        {"properties": [("mode", "TOGGLE")]},
    ),
    # (
    #     Operators.Select,
    #     {"type": "LEFTMOUSE", "value": "CLICK", "ctrl": True},
    #     {"properties": [("mode", "SUBTRACT")]},
    # ),
)

addon_keymaps = []


def register():
    pass


def unregister():
    pass
