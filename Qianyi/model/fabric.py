from bpy.props import FloatVectorProperty, FloatProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .model_data import ModelData, define_temp_prop


class Fabric(PropertyGroup, ModelData):
    thickness: FloatProperty(name="thickness", default=0.1)
    friction: FloatProperty(name="friction", default=0.03)
    weight: FloatProperty(name="weight", default=100., min=1.)
    # Display colour only: it is not part of the simulation payload, it is what
    # the pattern editor's "Solid" display mode fills the pattern with.
    color: FloatVectorProperty(
        name="Color",
        description="Colour this fabric's patterns are filled with in the pattern editor",
        subtype='COLOR',
        size=3,
        default=(0.85, 0.85, 0.9),
        min=0.0,
        max=1.0,
    )
    # cloth dynamic
    stretch: FloatVectorProperty(name="stretch", size=3, default=(1, 1, 1.),min=0.0,max=1.)
    # shear: FloatVectorProperty(name="shear", size=3, default=(1, 1, 1.),min=0.01,max=1.)
    bending: FloatVectorProperty(name="bending", size=3, default=(1, 1, 1.),min=0.01,max=1.)

    @property
    def project(self):
        return self.id_data


# define_temp_prop(Fabric, "project", None)

register, unregister = register_classes_factory((Fabric,))
