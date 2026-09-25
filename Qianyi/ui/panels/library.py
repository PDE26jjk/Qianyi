"""The GC library panel: browse the pattern components and add one to the project."""

import os

import bpy
from bpy.types import Context

from ...declarations import Operators, Panels
from ...patternlib import component, preview, registry
from ...patternlib.land import land_pattern
from ...utilities.node_tree import get_active_node_tree
from . import NODE_PT_qmyi_base

THUMBNAIL_COLUMNS = 4
THUMBNAIL_SCALE = 2.0
THUMBNAIL_SIZE = 64

_preview_icons: dict[str, int] = {}


def _infos():
    try:
        return registry.infos()
    except Exception as error:  # a broken component module must not kill the panel
        return str(error)


def _filtered(project, infos):
    """Components matching the search box and the category filter."""
    text = (project.library_filter or "").strip().lower()
    category = project.library_category
    shown = []
    # Deliberate Python loop: this walks a list of records to build a filtered
    # list of records, not a numeric array.
    for info in infos:
        if category != "ALL" and info.category.upper() != category:
            continue
        haystack = " ".join((info.label, info.category, info.description,
                             info.component_id, " ".join(info.params))).lower()
        if text and text not in haystack:
            continue
        shown.append(info)
    return shown


def _preview_icon_id(component_id: str) -> int:
    """A thumbnail of the component's first generation, created once per session."""
    cached = _preview_icons.get(component_id)
    if cached is not None:
        return cached
    icon_id = 0
    try:
        spec = component.build_component(component_id)
        image = preview.render_preview([land_pattern(pattern) for pattern in spec.patterns],
                                       size=THUMBNAIL_SIZE)
        name = f"qy_gc_preview_{component_id}"
        datablock = bpy.data.images.get(name)
        if datablock is None:
            datablock = bpy.data.images.new(name, THUMBNAIL_SIZE, THUMBNAIL_SIZE, alpha=True)
        datablock.pixels[:] = preview.to_pixels(image)
        datablock.preview_ensure()
        icon_id = datablock.preview.icon_id
    except Exception:
        icon_id = 0
    _preview_icons[component_id] = icon_id
    return icon_id


class QY_PT_gc_library(NODE_PT_qmyi_base):
    bl_category = "GC Library"
    bl_label = "GC Library"
    bl_idname = Panels.GcLibrary
    bl_order = 0

    def draw(self, context: Context):
        layout = self.layout
        project = get_active_node_tree(context)
        if project is None:
            layout.label(text="No project editing")
            return

        infos = _infos()
        if isinstance(infos, str):
            layout.label(text=f"Pattern library error: {infos}", icon="ERROR")
            return

        self._draw_filters(layout, project)
        reload_row = layout.row(align=True)
        reload_row.operator(Operators.ReloadComponents, icon="FILE_REFRESH")
        reload_errors = registry.errors()
        if reload_errors:
            box = layout.box()
            box.label(text=f"{len(reload_errors)} component file(s) failed to load",
                      icon="ERROR")
            # Deliberate Python loop: one row per failing file.
            for entry in reload_errors[:5]:
                box.label(text=f"{os.path.basename(entry['path'])}: {entry['error'][:60]}")

        shown = _filtered(project, infos)
        if not shown:
            layout.label(text="No component matches the filter")
        else:
            grid = layout.grid_flow(row_major=True, columns=THUMBNAIL_COLUMNS,
                                    even_columns=True, align=True)
            # Deliberate Python loop: one grid cell per component; every cell is
            # drawn as its own set of UI widgets.
            for info in shown:
                cell = grid.column(align=True)
                icon_id = _preview_icon_id(info.component_id)
                if icon_id:
                    cell.template_icon(icon_value=icon_id, scale=THUMBNAIL_SCALE)
                else:
                    cell.label(text="", icon="MESH_GRID")
                cell.operator(Operators.SelectLibraryComponent,
                              text=info.label).component_id = info.component_id
                if info.source != "builtin":
                    cell.label(text=info.source, icon="FILE_SCRIPT")

        self._draw_details(layout, project, infos)
        self._draw_generators(layout, project)

    def _draw_filters(self, layout, project):
        row = layout.row(align=True)
        row.prop(project, "library_filter", text="", icon="VIEWZOOM")
        row.prop(project, "library_category", text="")

    def _draw_details(self, layout, project, infos):
        box = layout.box()
        selected = next((info for info in infos
                         if info.component_id == project.library_component_id), None)
        if selected is None:
            box.label(text="Select a component to see its details")
            return
        header = box.row(align=True)
        header.label(text=selected.label, icon="MESH_GRID")
        header.label(text=selected.category)
        if selected.description:
            box.label(text=selected.description)
        column = box.column(align=True)
        # Deliberate Python loop: one row per parameter, drawn as UI widgets.
        for key, spec in selected.params.items():
            row = column.row(align=True)
            unit = spec.get("unit", "")
            bounds = ""
            if "min" in spec or "max" in spec:
                bounds = f"[{spec.get('min', '-')} .. {spec.get('max', '-')}]"
            row.label(text=str(spec.get("label", key)))
            row.label(text=f"{spec.get('default')} {unit}".strip())
            row.label(text=bounds)
        box.operator(Operators.AddGenerator, text="Add to Project",
                     icon="ADD").component_id = selected.component_id

    def _draw_generators(self, layout, project):
        layout.separator()
        layout.label(text=f"Generators in this project: {len(project.generators)}")
        row = layout.row()
        row.template_list("QY_UL_GeneratorList", "", project, "generators",
                          project, "active_generator_index", rows=4)


class QY_UL_GeneratorList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text="", icon="MODIFIER")
        row.prop(item, "name", emboss=False, text="")


class QY_PT_gc_generator_property(NODE_PT_qmyi_base):
    bl_parent_id = Panels.GcLibrary
    bl_idname = Panels.GcGeneratorProperty
    bl_label = "Parameters"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    def draw(self, context: Context):
        layout = self.layout
        project = get_active_node_tree(context)
        if project is None:
            return
        index = project.active_generator_index
        if not (0 <= index < len(project.generators)):
            layout.label(text="No generator selected")
            return
        generator = project.generators[index]
        try:
            label = registry.info(generator.component_id).label
        except Exception:
            label = generator.component_id
        column = layout.column(align=True)
        column.label(text=label or "Generator", icon="MODIFIER")
        # Deliberate Python loop: one widget per parameter of this generator.
        for param in generator.params:
            row = column.row(align=True)
            if param.kind == "bool":
                row.prop(param, "value_bool", text=param.label)
            elif param.kind == "int":
                row.prop(param, "value_int", text=param.label)
            elif param.kind == "text":
                row.prop(param, "value_text", text=param.label)
            else:
                row.prop(param, "value_float", text=param.label)
            if param.unit:
                row.label(text=param.unit)
        column.separator()
        column.operator(Operators.DetachGenerator, icon="UNLINKED")
