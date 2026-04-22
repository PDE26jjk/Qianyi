import logging

import bpy
from bpy.props import IntProperty, BoolProperty, PointerProperty, IntVectorProperty, EnumProperty
from bpy.types import PropertyGroup
from bpy.utils import register_class, unregister_class

from utilities.console import console_print
from .model_data import ModelData, define_temp_prop
from .simulation_data import SimulationProps


# logger = logging.getLogger(__name__)


class QianyiProps(PropertyGroup, ModelData):
    """The base structure for Qianyi"""

    # show_origin: BoolProperty(name="Show Origin Entities")

    version: IntVectorProperty(
        name="Extension Version",
        description="version this scene was saved with",
    )

    edit_mode: EnumProperty(
        name="Edit Mode",
        description="Edit Mode of Qianyi",
        items=[
            ('PATTERN', "Pattern", "Edit Pattern", 'MESH_PLANE', 0),
            ('EDGE', "Edge", "Edit Edge", 'MOD_EDGESPLIT', 1),
            ('SEWING', "Sewing", "Edit Sewing", 'CURVE_PATH', 2),
        ],
        default='PATTERN'
    )
    edit_sub_mode: EnumProperty(
        name="Edit sub Mode",
        description="Edit Submode of Qianyi",
        items=[
            ('EDGE_VERTEX', "EDGE_VERTEX", "", ),
            ('ADD_VERTEX', "ADD_VERTEX", "", ),
            ('ADD_SEWING1', "ADD_SEWING1", "", ),
            ('INTERNAL_POINT', "INTERNAL_POINT", "", ),
        ],
        default='EDGE_VERTEX'
    )
    simulation_data: bpy.props.CollectionProperty(type=SimulationProps)

    @property
    def simulation(self):
        if len(self.simulation_data) < 1:
            self.simulation_data.add()
        return self.simulation_data[0]

    def update_active_project_index(self, context):
        if len(bpy.data.node_groups) > self.active_project_index \
                and hasattr(context.space_data, "node_tree"):
            context.space_data.node_tree = bpy.data.node_groups[
                self.active_project_index
            ]

    active_project_index: bpy.props.IntProperty(
        default=0,
        min=0,
        name="Active Project",
        description="The project editing",
        update=update_active_project_index,
    )

    def set_hover_object(self, obj):
        self.set_temp_data_item("hover_object", obj)

    def clear_temp_data(self):
        self.set_hover_object(None)


define_temp_prop(QianyiProps, "hover_object", None)


def register():
    register_class(QianyiProps)
    bpy.types.Scene.qmyi = PointerProperty(type=QianyiProps)
    qmyi = bpy.context.scene.qmyi
    qmyi.simulation.enable_free_simulation = False
    qmyi.simulation.simulation_with_animation = False
    qmyi.hover_object = None
    # bpy.types.Object.qmyi_index = IntProperty(name="associated qianyi data", default=-1)


def unregister():
    # if hasattr(bpy.types.Object, "qmyi_index"):
    #     del bpy.types.Object.qmyi_index
    if hasattr(bpy.types.Scene, "qmyi"):
        del bpy.types.Scene.qmyi
    unregister_class(QianyiProps)
