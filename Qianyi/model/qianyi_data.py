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
            ('ADD_SEWING_FREE', "ADD_SEWING_FREE", "", ),
            ('EDIT_SEWING', "EDIT_SEWING", "", ),
            ('INTERNAL_POINT', "INTERNAL_POINT", "", ),
        ],
        default='EDGE_VERTEX'
    )
    show_grain_dir: BoolProperty(
        name="Show Grain Direction",
        description="Display the grain direction arrow in the pattern editor",
        default=False,
    )
    corner_mode: EnumProperty(
        name="Corner",
        description="Which corner treatment the corner tool applies: a round, "
                    "a chamfer, or a hollow cut into the pattern",
        items=[
            ("ROUND", "Round", "Replace the corner with an arc tangent to both "
                               "edges",),
            ("CHAMFER", "Chamfer", "Replace the corner with a straight edge "
                                   "between the same two points",),
            ("CONCAVE", "Hollow",
             "Put the arc on the other side of the chord, cutting a hollow "
             "into the pattern",),
        ],
        default='ROUND',
    )
    sync_selection: BoolProperty(
        name="Sync Selection",
        description="Keep the 3D selection and the pattern editor's selection in "
                    "step: selecting a pattern's mesh selects that pattern (and its "
                    "instance copies) in the pattern editor, and the other way "
                    "round. Works the way the UV editor's sync selection does",
        default=False,
    )
    spline_no_handles: BoolProperty(
        name="Spline without handles",
        description="Give an edge its handles back as vector handles - zeroed, "
                    "the way a spline is edited in other software - when a "
                    "control point is added to it, instead of keeping the curve "
                    "smooth through the new point",
        default=False,
    )
    triangulator: EnumProperty(
        name="Triangulator",
        description="Which triangulator the mesh sampler runs: gDel2D is the "
                    "mature one, gCDT the newer and faster one that is still "
                    "unstable on some inputs",
        items=[
            ('0', "gDel2D", "The mature triangulator (default)",),
            ('1', "gCDT", "The newer, faster triangulator; still unstable",),
        ],
        default='0',
    )
    mesh_profile: BoolProperty(
        name="Profile Mesh Build",
        description="Print what every phase of a mesh rebuild cost, in seconds",
        default=False,
    )
    pattern_display_mode: EnumProperty(
        name="Display",
        description="What the pattern editor draws for a pattern: the fabric "
                    "colour, the outline only, the sampled mesh, or the "
                    "engine's per-vertex stress / debug values",
        items=[
            ('SOLID', "Solid", "Fill each pattern with its fabric colour",),
            ('WIREFRAME', "Wireframe",
             "Draw outlines and internal lines only",),
            ('MESH', "Mesh", "Draw the sampled pattern mesh over the outline",),
            ('STRESS', "Stress",
             "Colour the mesh with the engine's per-vertex values",),
            ('DEBUG', "Debug",
             "Colour the mesh with the engine's debug values",),
        ],
        default='MESH',
    )
    view3d_vertex_colors: EnumProperty(
        name="Vertex Colors",
        description="Colour the simulated patterns in the 3D viewport by the "
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


def ensure_edit_mode(context, mode=None, sub_mode=None) -> bool:
    """Put the pattern editor into the mode a tool needs.

    Picking a tool says what the user wants to do next, so a tool activates its
    own mode instead of failing silently because the header happens to be on
    another one. Returns whether anything changed.
    """
    qmyi = getattr(getattr(context, "scene", None), "qmyi", None)
    if qmyi is None:
        return False
    changed = False
    if mode is not None and qmyi.edit_mode != mode:
        qmyi.edit_mode = mode
        changed = True
    if sub_mode is not None and qmyi.edit_sub_mode != sub_mode:
        qmyi.edit_sub_mode = sub_mode
        changed = True
    return changed


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
