# Please keep this file in alphabetical order
from enum import Enum


class Gizmos(str, Enum):
    Angle = "NODE_GT_slvs_angle"
    Constraint = "NODE_GT_slvs_constraint"
    ConstraintValue = "NODE_GT_slvs_constraint_value"
    Preselection = "NODE_GT_qmyi_preselection"


class GizmoGroups(str, Enum):
    Angle = "NODE_GGT_slvs_angle"
    Constraint = "NODE_GGT_slvs_constraint"
    Preselection = "NODE_GGT_qmyi_preselection"


class Operators(str, Enum):
    PatternMove2D = "qmyi.2d_pattern_move"
    PatternScale2D = "qmyi.2d_pattern_scale"
    PatternRotate2D = "qmyi.2d_pattern_rotate"
    Pick3D = "view3d.qmyi_pick3d"
    AddPoly = "node.qmyi_add_poly"
    Select = "node.qmyi_select"
    SelectAll = "node.qmyi_select_all"
    SelectBox = "node.qmyi_select_box"
    # SelectInvert = "node.qmyi_select_invert"
    SelectExtendAll = "node.qmyi_select_extend_all"
    SelectExtend = "node.qmyi_select_extend"
    ContextMenu = "node.qmyi_context_menu"
    ConvertCurve = "node.qmyi_convert_curve"
    GenerateAllMesh = "node.qmyi_generate_all_mesh"
    AddProject = "qmyi.add_project"
    AddFabric = "qmyi.add_fabric"
    RemoveProject = "qmyi.remove_project"
    RemovePattern = "qmyi.remove_pattern"
    RemoveFabric = "qmyi.remove_fabric"
    ChangeProjectOrder = "qmyi.change_project_order"
    ChangePatternOrder = "qmyi.change_pattern_order"
    ChangeFabricOrder = "qmyi.change_fabric_order"
    Import = "node.qmyi_import"
    Export = "node.qmyi_Export"


class Macros(str, Enum):
    DuplicateMove = "node.slvs_duplicate_move"


class Menus(str, Enum):
    SelectedMenu = "NODE_MT_selected_menu"


class Panels(str, Enum):
    QianyiNodeTree = "QianyiNodeTree"
    Entities = "NODE_PT_QianyiEntities"
    Projects = "NODE_PT_QianyiProjects"
    Patterns = "NODE_PT_QianyiPatterns"
    Fabrics = "NODE_PT_QianyiFabric"
    PatternProperty = "NODE_PT_QianyiPatternProperty"
    FabricProperty = "NODE_PT_QianyiFabricProperty"
    InOut = "NODE_PT_QianyiINOUT"
    Simulation = "NODE_PT_QianyiSimulation"
    SimulationObject = "NODE_PT_QianyiSimulationObject"

class VisibilityTypes(str, Enum):
    Hide = "HIDE"
    Show = "SHOW"


class WorkSpaceTools(str, Enum):
    AddPoly = "qmyi.add_poly"
    Select = "qmyi.select"
    PickMesh = "qmyi.pick_mesh"

