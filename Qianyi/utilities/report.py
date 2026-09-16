"""Tell the user about a problem, in a UI session or in a background one.

Every message also goes to the console: a background session has no window
manager to pop a menu up, and the console line is then the only report there
is, so it must never be the fallback that is skipped.
"""

import bpy

from .console import console


def report_error(message, details=(), title="Error"):
    """Show `message` and optional detail lines to the user.

    Returns True when a popup was shown, False when only the console got it.
    """
    details = list(details or ())
    console.error(message)
    for line in details:
        console.error("    " + line)

    # A background session has no window to pop a menu up in, and asking for one
    # crashes Blender outright, so the console line above is the whole report.
    if bpy.app.background:
        return False

    def draw(self, _context):
        self.layout.label(text=message, icon="ERROR")
        for line in details:
            self.layout.label(text=line)

    try:
        bpy.context.window_manager.popup_menu(draw, title=title, icon="ERROR")
        return True
    except Exception as error:
        console.warning("popup is not available here:", error)
        return False
