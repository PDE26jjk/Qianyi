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
        Operators.PatternRotate2D,
        {"type": "R", "value": "PRESS"},
        None,
    ),
    (
        Operators.PatternScale2D,
        {"type": "S", "value": "PRESS"},
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

# The editor's own right-click menu. Every tool of the pattern editor shows it,
# so the commands it offers - the per-mode ones especially - are reachable from
# the tool the user is working with rather than only from the selection tool.
tool_context_menu = (
    (
        Operators.ContextMenu,
        {"type": "RIGHTMOUSE", "value": "PRESS"},
        {"properties": [("delayed", False)]},
    ),
)

tool_generic = (
    *tool_base_keymap,
    *tool_context_menu,
    *tool_use_select,
    *tool_access,
)

tool_select = (
    *tool_base_keymap,
    *tool_access,
    *tool_context_menu,
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
    (
        Operators.SelectBox,
        {"type": "LEFTMOUSE", "value": "CLICK_DRAG"},
        None,
    ),
    (
        Operators.SelectBox,
        {"type": "LEFTMOUSE", "value": "CLICK_DRAG", "ctrl": True},
        {"properties": [("mode", "SUBTRACT")]},
    ),
    (
        Operators.SelectBox,
        {"type": "LEFTMOUSE", "value": "CLICK_DRAG", "shift": True},
        {"properties": [("mode", "EXTEND")]},
    )
)

addon_keymaps = []


def register():
    pass


def unregister():
    pass
