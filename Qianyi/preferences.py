"""Add-on preferences: where user pattern components live."""

import os

import bpy
from bpy.props import StringProperty
from bpy.utils import register_classes_factory

PACKAGE_NAME = __package__


class QianyiPreferences(bpy.types.AddonPreferences):
    bl_idname = PACKAGE_NAME

    components_path: StringProperty(
        name="Component Folders",
        subtype="DIR_PATH",
        description="Folders with pattern component modules (*.py declaring COMPONENT_ID); "
                    "separate several folders with the platform path separator",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Pattern components")
        layout.prop(self, "components_path")
        layout.label(text=f"Several folders: separate them with '{os.pathsep}'")
        layout.operator("qmyi.reload_components", icon="FILE_REFRESH")


def component_paths() -> list[str]:
    """The folders configured in the preferences, or an empty list."""
    try:
        addon = bpy.context.preferences.addons.get(PACKAGE_NAME)
        preferences = getattr(addon, "preferences", None)
        if preferences is None:
            return []
        raw = preferences.components_path or ""
    except Exception:
        return []
    return [piece.strip() for piece in raw.split(os.pathsep) if piece.strip()]


register, unregister = register_classes_factory((QianyiPreferences,))
