import bpy
from bpy.types import Context

from ...utilities.node_tree import get_active_node_tree
from ...declarations import Panels,Operators
from . import NODE_PT_qmyi_base



class QY_PT_patterns(NODE_PT_qmyi_base):
    bl_category = "Pattern"
    bl_label = "Patterns"
    bl_idname = Panels.Patterns
    # bl_options = {""}
    bl_order = 0

    def draw(self, context: Context):
        layout = self.layout
        # qmyi = context.scene.qmyi
        row = layout.row(align=False)
        project = get_active_node_tree(context)
        if project is None:
            row.label("No project editing")
            return
        # box = layout.box()
        pattern = None
        if project.active_pattern_index < len(project.patterns):
            pattern = project.patterns[project.active_pattern_index]
        col = row.column(align=True)
        col.template_list(QY_UL_PatternList.__name__, "Patterns", project, "patterns", project, "active_pattern_index", rows=4)
        col = row.column(align=True)

        subrow = col.row(align=True)
        subrow.enabled = pattern is not None
        subrow.operator(Operators.RemovePattern, text="", icon="REMOVE")
        col.separator()
        subrow = col.row(align=True)
        subrow.enabled = pattern is not None and filter_name[None] == ""
        subrow.operator(Operators.ChangePatternOrder, text="", icon="TRIA_UP").move_up = True
        subrow = col.row(align=True)
        subrow.enabled = pattern is not None and filter_name[None] == ""
        subrow.operator(Operators.ChangePatternOrder, text="", icon="TRIA_DOWN").move_up = False


filter_name = {None:""}


class QY_UL_PatternList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.label(text="", icon="SCRIPT")
        row.prop(item, "name", emboss=False, text="")

    def filter_items(self, context, data, propname):
        global filter_name
        # qmyi = context.scene.qmyi
        patterns = getattr(data, propname)
        helper_funcs = bpy.types.UI_UL_list

        flt_flags = []

        if self.filter_name:
            flt_flags = helper_funcs.filter_items_by_name(self.filter_name, self.bitflag_filter_item, patterns, "name",
                                                          reverse=False)
        if not flt_flags:
            flt_flags = [self.bitflag_filter_item] * len(patterns)

        filter_name[None] = self.filter_name

        return flt_flags, []



class QY_PT_patternProperty(NODE_PT_qmyi_base):
    bl_parent_id = Panels.Patterns
    bl_idname = Panels.PatternProperty
    bl_label = "Property"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    # bl_category = "Pattern"
    # bl_options = {"DEFAULT_CLOSED", "HEADER_LAYOUT_EXPAND"}
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        project = get_active_node_tree(context)
        row = layout.row()
        if project is None:
            return
        # box = layout.box()
        pattern = None
        if project.active_pattern_index < len(project.patterns):
            pattern = project.patterns[project.active_pattern_index]
        else:
            return

        col = layout.column(align=True)
        col.prop(pattern, "granularity")
        col.prop(pattern, "anchor")

        col = layout.column(align=False)
        col.prop(pattern, "rotation")

