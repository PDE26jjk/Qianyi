"""Turn one or more seam halves round: the same span, sewn the other way.

A half records the two places of its chain it runs between, and the direction it
runs in. The two halves of a seam are stitched in the order each was drawn in, so
that direction is what decides which end of one pattern meets which end of the
other: a seam whose ends are paired the wrong way is fixed by turning a half
round, which covers the same stretch of the chain and reads it from its far end.

The command acts on the halves the sewing selection names, and on the half under
the pointer when the selection names none, so a right click on a half is enough.
"""

from bpy.types import Context
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators
from ..model.sewing import SewingOneSide
from ..utilities.console import console
from ..utilities.node_tree import get_active_node_tree
from ._2d_operator_base import Operator2DBase


def halves_to_turn(project) -> list:
    """The halves this command acts on: the selected ones, or the pointed one."""
    halves = [obj for obj in project.get_selected_objects_by_mode("SEWING", strict=False)
              if isinstance(obj, SewingOneSide)]
    if halves:
        return halves
    manager = global_data.temp_draw_manager
    pick = manager.hover_pick if manager is not None else None
    if pick is not None and isinstance(pick[2], SewingOneSide):
        return [pick[2]]
    return []


class NODE_OT_sewing_reverse(Operator2DBase):
    """Turn the selected seam halves round"""

    bl_idname = Operators.SewingReverse2D
    bl_label = "reverse the half"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: Context):
        project = get_active_node_tree(context)
        if project is None or context.scene.qmyi.edit_mode != "SEWING":
            return False
        halves = halves_to_turn(project)
        if not halves:
            return False
        return True

    def execute(self, context: Context):
        project = get_active_node_tree(context)
        if project is None or context.scene.qmyi.edit_mode != "SEWING":
            return {'CANCELLED'}
        halves = halves_to_turn(project)
        if not halves:
            console.info("reverse the half: no seam half is selected or pointed at")
            return {'CANCELLED'}
        seams = []
        for side in halves:  # loop: one half per write
            side.turn_round()
            seam = side.sewing
            if seam is not None and seam not in seams:
                seams.append(seam)
        # Turning a half round changes the order its seam is stitched in, so the
        # component is linked again - and the guard looks at it, which flags a
        # seam this left impossible instead of letting the mesh path find it.
        # A half the linker will not have goes back to what it was.
        try:
            project.sewings_changed(project.patterns_of(seams))
        except Exception as refused:  # noqa: BLE001 - the linker's reason is the answer
            for side in halves:
                side.turn_round()
            try:
                project.sewings_changed(project.patterns_of(seams))
            except Exception as again:  # noqa: BLE001
                console.warning("reverse the half: the seam graph could not be linked "
                                "again:", again)
            console.warning("reverse the half: that was refused:", refused)
            return {'CANCELLED'}
        for seam in seams:  # loop: one redraw per seam that changed
            seam.need_render_update = True
            seam.update()
        console.info(f"reverse the half: turned {len(halves)} half round")
        if context.area is not None:
            context.area.tag_redraw()
        return {'FINISHED'}


register, unregister = register_classes_factory((NODE_OT_sewing_reverse,))
