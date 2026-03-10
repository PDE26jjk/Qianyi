from ..utilities.register import module_register_factory

modules = [
    "select",
    "project",
    "pattern_panel",
    "fabric_panel",
    "in_out",
    "mesh",
    "TestOperator",
    "context_menu",
    "ConvertCurveOperator",
    '_2d_pattern_move',
    '_3d_pick_mesh',
]

register, unregister = module_register_factory(__name__, modules)
