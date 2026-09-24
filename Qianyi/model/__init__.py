from ..utilities.register import module_register_factory

modules = [
    "geometry",
    "internal_line",
    "sketch",
    "generator",
    "pattern",
    "fabric",
    "sewing",
    "simulation_data",
    "solver_params",
    "obj_sim_data",
    "qianyi_data",
    "qianyi_project",
    "undo_redo"
]


register, unregister = module_register_factory(__name__, modules)
