from .utilities.register import module_register_factory

core_modules = [
    "model",
    "operators",
    "gizmos",
    "ui",
    "draw_editor",
    "workspacetools",
    "vr"
]

register_full, unregister_full = module_register_factory(__package__, core_modules)
