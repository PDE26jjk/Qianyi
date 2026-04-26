import bpy
import numpy as np
from bpy.props import BoolProperty, FloatProperty, IntProperty, FloatVectorProperty, EnumProperty
from bpy.types import Panel, PropertyGroup

from .. import global_data
from utilities.console import console_print, console


class ObjectSimulationProperties(PropertyGroup):
    participate_in_simulation: BoolProperty(
        name="participate_in_simulation",
        description="Does this object participate in physical simulation?",
        default=False,
        update=lambda self_, context: self_._on_participate_in_simulation_toggle(context)
    )

    vertices_updated_every_frame: BoolProperty(
        name="vertices_updated_every_frame",
        description="Vertices of mesh updated every frame.",
        default=False,
    )

    simulation_index: IntProperty(
        name="simulationIndex",
        # options={'SKIP_SAVE'},
    )
    pattern_uuid: IntProperty(default=-1)

    base_key_name = 'QYBasis'
    simulation_key_name = 'QYSim'

    fix_pin_group_name = 'QYPinFix'
    attach_pin_group_name = 'QYPinAttach'

    @property
    def is_pattern_mesh(self):
        return self.pattern_uuid != -1

    @property
    def pattern(self):
        if self.is_pattern_mesh:
            p = global_data.get_obj_by_uuid(self.pattern_uuid, False)
            if p is None:
                raise ValueError(f"Can not find pattern_uuid: {self.pattern_uuid}")
            return p
        return None

    @pattern.setter
    def pattern(self, val):
        self.pattern_uuid = val.global_uuid

    def _on_participate_in_simulation_toggle(self, context):
        if self.participate_in_simulation:
            console_print(self.id_data.name, "join simulation")
        else:
            console_print("out simulation")

    def remove_shape_key(self, key):
        obj = self.id_data
        mesh: bpy.types.Mesh = obj.data
        if mesh.shape_keys is None:
            return
        if key not in mesh.shape_keys.key_blocks:
            return
        obj.shape_key_remove(mesh.shape_keys.key_blocks[key])

    def get_shape_key_vertices(self, key):
        obj = self.id_data
        if not self.is_pattern_mesh:
            return None
        mesh: bpy.types.Mesh = obj.data
        if mesh.shape_keys is None:
            return None
        keys = mesh.shape_keys.key_blocks
        if key not in keys:
            return None
        shape_key = mesh.shape_keys.key_blocks[key]
        num_vertices = len(mesh.vertices)
        vertices_local = np.empty(num_vertices * 3, dtype=np.float32)
        shape_key.points.foreach_get("co", vertices_local)
        return vertices_local.reshape(-1, 3)

    def get_simulation_vertices(self):
        vertices = self.get_shape_key_vertices(self.simulation_key_name)
        return vertices

    def set_simulation_vertices(self, vertices):
        obj = self.id_data
        mesh: bpy.types.Mesh = obj.data
        num_vertices = len(mesh.vertices)
        if vertices.shape[0] != num_vertices:
            raise ValueError(
                f"Number of vertices does not match: {vertices.shape[0]} != {num_vertices}")
        self._ensure_shape_key()
        shape_key = mesh.shape_keys.key_blocks[self.simulation_key_name]
        # console.info(vertices.shape)
        vertices = vertices.ravel()
        shape_key.points.foreach_set("co", vertices)

    def get_pattern_vertices(self):
        vertices = self.get_shape_key_vertices(self.base_key_name)
        if vertices is not None:
            vertices = np.ascontiguousarray(vertices[:, :2])  # (x,y,z) -> (x,y)
        return vertices

    def ensure_attributes(self):
        obj = self.id_data
        if not self.is_pattern_mesh:
            return
        if self.is_pattern_mesh:
            if self.pattern.mesh_object != obj:
                console_print(f"ERROR:{obj.name} != self.pattern.mesh_object ({self.pattern.mesh_object.name})")
                self.pattern_uuid = -1
                import traceback
                console_print(''.join(traceback.format_stack(limit=10)))
                return
        self._ensure_shape_key()
        self._ensure_vertex_group()

    def _ensure_shape_key(self):
        obj = self.id_data
        mesh: bpy.types.Mesh = obj.data
        if mesh.shape_keys is None:
            obj.shape_key_add(name='Basis')
        keys = mesh.shape_keys.key_blocks
        base_name = self.base_key_name
        if base_name not in keys:
            obj.shape_key_add(name=base_name, from_mix=True)
            keys[base_name].value = 1.0
        keys['Basis'].lock_shape = True
        keys[base_name].lock_shape = True

        sim_name = self.simulation_key_name
        if sim_name not in keys:
            obj.shape_key_add(name=sim_name, from_mix=False)
            keys[sim_name].value = 1.0
            keys[sim_name].relative_key = keys[base_name]

        color_attributes = mesh.color_attributes
        color_name = 'Color'
        if color_name not in color_attributes:
            color_attributes.new(
                name=color_name,
                type='FLOAT_COLOR',
                domain='POINT',
            )

    def _ensure_vertex_group(self):
        obj = self.id_data
        if self.fix_pin_group_name not in obj.vertex_groups:
            obj.vertex_groups.new(name=self.fix_pin_group_name)
        if self.attach_pin_group_name not in obj.vertex_groups:
            obj.vertex_groups.new(name=self.attach_pin_group_name)

    def get_vertex_group_weight(self, key):  # TODO make it faster
        obj = self.id_data
        weights_np = np.zeros(len(obj.data.vertices), dtype=np.float32)
        vg_index = -1
        if key not in obj.vertex_groups:
            return weights_np
        else:
            vg_index = obj.vertex_groups[key].index

        for i, v in enumerate(obj.data.vertices):
            for g in v.groups:
                if g.group == vg_index:
                    weights_np[i] = g.weight
                    break
        return weights_np

    def init_simulation(self, obj):
        if not obj or obj.type != 'MESH' or not self.is_pattern_mesh:
            return False

        self.ensure_attributes(obj)

        return True

    fabric_enum: bpy.props.EnumProperty(
        name="Fabric",
        description="Select fabric",
        items=lambda self_, context: self_.get_fabric_items(),
        # update=lambda self_, context: console_print(self.fabric_enum),
        get=lambda self_: self_.get_fabric_enum_value(),
        set=lambda self_, value: self_.set_fabric_enum_value(value),
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
