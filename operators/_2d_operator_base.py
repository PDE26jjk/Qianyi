from bpy.types import Operator, Context
from ..utilities.node_tree import get_active_node_tree


class Operator2DBase(Operator):

    @classmethod
    def poll(cls, context: Context):
        return get_active_node_tree(context) is not None


