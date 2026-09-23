from ..utilities.register import module_register_factory

modules = [
    "select",
    "select_box",
    "project",
    "pattern_panel",
    "fabric_panel",
    "generator",
    "in_out",
    "mesh",
    "TestOperator",
    "context_menu",
    "ConvertCurveOperator",
    '_2d_pattern_move',
    '_2d_pattern_rotate',
    '_2d_pattern_scale',
    '_2d_pattern_create_by_pen',
    '_2d_internal_line_create_by_pen',
    '_2d_pattern_copy_instance',
    '_2d_elements_delete',
    '_2d_edge_mode_move',
    '_2d_add_vertex',
    '_2d_add_spline_point',
    '_2d_divide_edge',
    '_2d_corner',
    '_2d_fan',
    '_2d_add_sewing_1to1',
    '_3d_pick_mesh',
    'capture_scene',
]

register, unregister = module_register_factory(__name__, modules)
