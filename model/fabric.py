from bpy.props import FloatVectorProperty, FloatProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .model_data import ModelData, define_temp_prop


class Fabric(PropertyGroup, ModelData):
    thickness: FloatProperty(name="thickness", default=0.1)
    friction: FloatProperty(name="friction", default=0.03)
    weight: FloatProperty(name="weight", default=100.)
    # cloth
    stretch: FloatVectorProperty(name="stretch", size=3, default=(1, 1, 1.))
    shear: FloatVectorProperty(name="shear", size=3, default=(1, 1, 1.))
    bending: FloatVectorProperty(name="bending", size=3, default=(1, 1, 1.))

    @property
    def project(self):
        return self.id_data


# define_temp_prop(Fabric, "project", None)

register, unregister = register_classes_factory((Fabric,))
