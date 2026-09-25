import bpy
from bpy.types import Operator, Context

from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree


class Operator2DBase(Operator):

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None


def show_redo_panel(context: Context) -> None:
    """Ask for Blender's own redo panel once an operator has returned.

    Blender draws that panel only when asked (`screen.redo_last`), and the entry
    points it draws itself are the F9 keymap and the Edit menu; a command that
    runs from a context menu - or from the end of a modal drag - has neither in
    front of the user. The redo state only exists after the operator has
    returned, so the request is deferred to the next event loop turn rather than
    made from inside `execute`.

    Only the window is held across the delay. An operator that ran from a
    popup menu sees the menu's own region in its context, and that region dies
    with the menu - handing it to a `temp_override` after the menu closed is
    what used to crash the popup the moment it was asked for. The editor area
    is resolved again when the timer runs, from the window's live screen.
    """
    window = getattr(context, "window", None)
    if window is None:
        return

    def request():
        try:
            # The window may have closed within the delay.
            if window not in bpy.context.window_manager.windows.values():
                return None
            screen = window.screen
            area = next((node_editor for node_editor in screen.areas
                         if node_editor.type == 'NODE_EDITOR'), None)
            region = next((window_region for window_region in area.regions
                           if window_region.type == 'WINDOW'), None) \
                if area is not None else None
            if region is None:
                return None
            # `screen` has to be overridden as well: the redo operator's poll
            # reads the context's screen, not the window's, and a timer has no
            # screen of its own.
            with bpy.context.temp_override(window=window, screen=screen,
                                           area=area, region=region):
                bpy.ops.screen.redo_last('INVOKE_DEFAULT')
        except Exception as error:
            console.warning("could not open the redo panel:", error)
        return None  # one shot

    # A moment later, so the events that are still in flight from the menu or
    # the key press cannot close the popup the moment it opens.
    bpy.app.timers.register(request, first_interval=0.1)


def select_edges(project, uuids) -> int:
    """Leave these edges selected, and nothing else.

    The result of a command is what the next one works on, and the pattern
    editor draws its selection, so the edges a command produced stay visible
    instead of the pattern appearing to have lost its selection.
    """
    project.selected_edges.clear()
    count = 0
    for uuid_value in uuids:  # loop: one selection entry per produced edge
        entry = project.selected_edges.add()
        entry.uuid = uuid_value
        count += 1
    return count


def select_vertices(project, vertices) -> int:
    """Leave these vertices selected, and nothing else.

    A point-driven tool takes its target from what the pointer is on, and the
    command it runs takes its target from the selection: selecting the vertex
    the click landed on is what joins the two, and it is also what lets the
    redo panel re-run the command from the state it was made in.
    """
    project.selected_vertices.clear()
    count = 0
    for vertex in vertices:  # loop: one selection entry per vertex
        vertex.is_selected = True
        entry = project.selected_vertices.add()
        entry.uuid = vertex.global_uuid
        count += 1
    return count

