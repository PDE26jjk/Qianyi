import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, FloatVectorProperty, EnumProperty
from bpy.types import Panel, PropertyGroup

from .. import global_data
from utilities.console import console_print


class ObjectSimulationProperties(PropertyGroup):
    participate_in_simulation: BoolProperty(
        name="participate_in_simulation",
        description="Does this object participate in physical simulation?",
        default=False,
        update=lambda self, context: self._on_participate_in_simulation_toggle(context)
    )

    simulation_index: IntProperty(
        name="simulationIndex",
        # options={'SKIP_SAVE'},
    )
    pattern_uuid: IntProperty(default=-1)

    # @property
    # def object_type(self):
    #     return ""

    @property
    def is_pattern_mesh(self):
        return self.pattern_uuid != -1

    @property
    def pattern(self):
        if self.is_pattern_mesh:
            return global_data.get_obj_by_uuid(self.pattern_uuid)
        return None

    @pattern.setter
    def pattern(self, val):
        self.pattern_uuid = val.global_uuid

    def _on_participate_in_simulation_toggle(self, context):
        if self.participate_in_simulation:
            console_print("join simulation")
            self.init_simulation(context.object)
        else:
            console_print("out simulation")

    def ensure_shape_keys(self, obj):
        mesh: bpy.types.Mesh = obj.data
        if mesh.shape_keys is None:
            obj.shape_key_add(name='Basis')
        keys = mesh.shape_keys.key_blocks
        base_name = 'QYBasis'
        if base_name not in keys:
            obj.shape_key_add(name=base_name, from_mix=True)
            keys[base_name].value = 1.0
        keys['Basis'].lock_shape = True
        keys[base_name].lock_shape = True

        sim_name = 'QYSim'
        if sim_name not in keys:
            obj.shape_key_add(name=sim_name, from_mix=False)
            keys[sim_name].value = 1.0
            keys[sim_name].relative_key = keys[base_name]

    def init_simulation(self, obj):
        if not obj or obj.type != 'MESH' or not self.is_pattern_mesh:
            return False

        self.ensure_shape_keys(obj)

        return True

    fabric_enum: bpy.props.EnumProperty(
        name="Fabric",
        description="Select fabric",
        items=lambda self, context: self.get_fabric_items(),
        # update=lambda self, context: console_print(self.fabric_enum),
        get=lambda self: self.get_fabric_enum_value(),
        set=lambda self, value: self.set_fabric_enum_value(value),
        options={"SKIP_SAVE"}
    )

    def get_fabric_items(self):
        if not self.pattern:
            return []
        items = []
        for i, fabric in enumerate(self.pattern.project.fabrics):
            # console_print(str(fabric.global_uuid), fabric.name, i)
            items.append((str(i), fabric.name, f"UUID: {fabric.global_uuid}", '', i))
        # console_print(items)
        return items

    def get_fabric_enum_value(self):
        for i, fabric in enumerate(self.pattern.project.fabrics):
            if fabric.global_uuid == self.pattern.fabric.global_uuid:
                # console_print("get",i)
                return i
        raise ValueError(f"Can not find fabric")
        # return -1

    def set_fabric_enum_value(self, value):
        # console_print( self.pattern.project.fabrics[value])
        self.pattern.fabric = self.pattern.project.fabrics[value]


classes = (
    ObjectSimulationProperties,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.qmyi_simulation_props = bpy.props.PointerProperty(type=ObjectSimulationProperties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Object.qmyi_simulation_props
