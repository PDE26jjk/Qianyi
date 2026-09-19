import logging

import bpy
from bpy.props import (IntProperty, BoolProperty, PointerProperty, IntVectorProperty,
                       EnumProperty, FloatProperty, FloatVectorProperty)
from bpy.types import PropertyGroup
from bpy.utils import register_class, unregister_class

from ..utilities.console import console_print
from .model_data import ModelData, define_temp_prop
from .simulation_data import SimulationProps
from .solver_params import CaptureProps, SolverParams


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
            ('ADD_SPLINE_POINT', "ADD_SPLINE_POINT", "", ),
            ('ADD_SEWING1', "ADD_SEWING1", "", ),
            ('INTERNAL_POINT', "INTERNAL_POINT", "", ),
        ],
        default='EDGE_VERTEX'
    )
    show_grain_dir: BoolProperty(
        name="Show Grain Direction",
        description="Display the grain direction arrow in the pattern editor",
        default=False,
    )
    sync_selection: BoolProperty(
        name="Sync Selection",
        description="Keep the 3D selection and the pattern editor's selection in "
                    "step: selecting a panel's mesh selects that panel (and its "
                    "instance copies) in the pattern editor, and the other way "
                    "round. Works the way the UV editor's sync selection does",
        default=False,
    )
    pattern_display_mode: EnumProperty(
        name="Display",
        description="What the pattern editor draws for a panel: the fabric "
                    "colour, the outline only, the sampled mesh, or the "
                    "engine's per-vertex stress / debug values",
        items=[
            ('SOLID', "Solid", "Fill each panel with its fabric colour",),
            ('WIREFRAME', "Wireframe",
             "Draw outlines and internal lines only",),
            ('MESH', "Mesh", "Draw the sampled panel mesh over the outline",),
            ('STRESS', "Stress",
             "Colour the mesh with the engine's per-vertex values",),
            ('DEBUG', "Debug",
             "Colour the mesh with the engine's debug values",),
        ],
        default='MESH',
    )
    view3d_vertex_colors: EnumProperty(
        name="Vertex Colors",
        description="Colour the simulated panels in the 3D viewport by the "
                    "editor's per-vertex strain or by the engine's debug values, "
                    "drawn as an overlay over the material Blender renders",
        items=[
            ('OFF', "Off", "Leave the viewport as Blender draws it"),
            ('STRESS', "Stress",
             "Colour each vertex by its strain, relative to the flat pattern"),
            ('DEBUG', "Debug",
             "Colour each vertex with the engine's debug values"),
        ],
        default='OFF',
    )
    view3d_seams: BoolProperty(
        name="Seams",
        description="Draw a line between each paired stitch vertex in the 3D "
                    "viewport, depth tested against the cloth",
        default=False,
    )
    view3d_seam_width: FloatProperty(
        name="Seam Width",
        default=2.0,
        min=0.5,
        max=8.0,
    )
    view3d_hud: BoolProperty(
        name="Simulation HUD",
        description="Show the run state and the real-time speed while a "
                    "simulation is running",
        default=True,
    )
    interactive_self_intersection_check: BoolProperty(
        name="Check Self-Intersection",
        description="Test a pattern outline for a self-crossing while it is "
                    "edited interactively (pen, add vertex, moved edge, delete) "
                    "and refuse the edit when it crosses. This is the only place "
                    "the check is optional: a mesh and a simulation are always "
                    "tested, whatever this is set to",
        default=True,
    )
    simulation_data: bpy.props.CollectionProperty(type=SimulationProps)

    solver: bpy.props.PointerProperty(
        name="Solver",
        description="Solver name and parameter block used by the engine",
        type=SolverParams,
    )
    capture: bpy.props.PointerProperty(
        name="Capture",
        description="Scene capture settings",
        type=CaptureProps,
    )

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
