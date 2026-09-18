"""Operators for parametric panel generators."""

import bpy
from bpy.props import StringProperty
from bpy.utils import register_classes_factory

from .. import generators
from .. import preferences
from ..declarations import Operators
from ..panellib import registry
from ..utilities.node_tree import get_active_node_tree


class QY_OT_AddGenerator(bpy.types.Operator):
    bl_idname = Operators.AddGenerator
    bl_label = "Add Generator"
    bl_description = "Add this panel generator to the project"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    component_id: StringProperty(default="", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        if not self.component_id:
            self.report({"ERROR"}, "no panel component selected")
            return {"CANCELLED"}
        try:
            generator = generators.create_generator(project, self.component_id)
        except Exception as error:  # a broken component must not kill the UI
            self.report({"ERROR"}, f"could not build '{self.component_id}': {error}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"added {generator.name} with {len(generator.outputs)} panel(s)")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class QY_OT_DetachGenerator(bpy.types.Operator):
    bl_idname = Operators.DetachGenerator
    bl_label = "Detach"
    bl_description = "Turn this generator's panels into ordinary panels"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        index = project.active_generator_index
        if not (0 <= index < len(project.generators)):
            return {"CANCELLED"}
        panels = generators.detach_generator(project, project.generators[index])
        self.report({"INFO"}, f"detached {len(panels)} panel(s)")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class QY_OT_SelectLibraryComponent(bpy.types.Operator):
    bl_idname = Operators.SelectLibraryComponent
    bl_label = "Select Component"
    bl_description = "Show this component's details in the library panel"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    component_id: StringProperty(default="", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None

    def execute(self, context):
        project = get_active_node_tree(context)
        project.library_component_id = self.component_id
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class QY_OT_ReloadComponents(bpy.types.Operator):
    bl_idname = Operators.ReloadComponents
    bl_label = "Reload Components"
    bl_description = ("Re-read the component folders from the preferences, so a component "
                      "being edited can be tried without restarting Blender")
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        errors = registry.reload_all(preferences.component_paths())
        if errors:
            for entry in errors:
                self.report({"ERROR"}, f"{entry['path']}: {entry['error']}")
        else:
            count = len(registry.infos())
            self.report({"INFO"}, f"component library reloaded, {count} component(s)")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (QY_OT_AddGenerator, QY_OT_DetachGenerator, QY_OT_SelectLibraryComponent,
     QY_OT_ReloadComponents)
)
