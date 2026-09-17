import bpy

from .header import header_append, header_prepend
from .menus import NODE_MT_CustomMenu
from .panels.entities import QY_PT_qmyi_entities
from .panels.fabrics import QY_UL_FabricList, QY_PT_fabricProperty, QY_PT_fabrics
from .panels.in_out import NODE_PT_qmyi_in_out
from .panels.patterns import QY_PT_patterns, QY_UL_PatternList, QY_PT_patternProperty
from .panels.library import (QY_PT_gc_library, QY_PT_gc_generator_property,
                             QY_UL_GeneratorList)
from .panels.projects import QY_PT_qmyi_projects, QY_UL_ProjectList
from .panels_3d.simulation import QY_PT_simulation, SimulationNextNframesOperator, SimulationToNframesOperator
from .panels_3d.simulation_object import QY_PT_simulation_object, SimulationDataRefreshOperator
from .panels_3d import simulation_params

classes = [
    NODE_MT_CustomMenu,
    QY_UL_ProjectList,
    QY_PT_qmyi_projects,
    QY_PT_patterns,
    QY_UL_PatternList,
    QY_PT_patternProperty,
    QY_PT_fabrics,
    QY_UL_FabricList,
    QY_PT_fabricProperty,
    QY_PT_gc_library,
    QY_UL_GeneratorList,
    QY_PT_gc_generator_property,
    QY_PT_qmyi_entities,
    NODE_PT_qmyi_in_out,
    QY_PT_simulation,
    SimulationDataRefreshOperator,
    SimulationNextNframesOperator,
    SimulationToNframesOperator,
    QY_PT_simulation_object,
    *simulation_params.classes,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.NODE_HT_header.append(header_append)
    bpy.types.NODE_MT_editor_menus.append(header_prepend)
    # bpy.types.NODE_PT_active_node_generic.append(node_info_append)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    bpy.types.NODE_MT_editor_menus.remove(header_prepend)
    bpy.types.NODE_HT_header.remove(header_append)
    # bpy.types.NODE_PT_active_node_generic.remove(node_info_append)
