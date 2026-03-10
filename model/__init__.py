from ..utilities.register import module_register_factory

modules = [
    "geometry",
    "pattern",
    "fabric",
    "sewing",
    "simulation_data",
    "obj_sim_data",
    "qianyi_data",
    "qianyi_project",
    "undo_redo"
]


register, unregister = module_register_factory(__name__, modules)
