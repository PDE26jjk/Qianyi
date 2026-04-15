import sys
from enum import Enum

from mathutils import Vector

from utilities.console import Console, console

# from .gizmos.temp_draw_manager import TempDrawManager

temp_draw_manager: 'TempDrawManager' = None

temp_data = []
uuid2obj = {}


def get_obj_by_uuid(uuid, check_uuid=True):
    if uuid in uuid2obj:
        obj = uuid2obj[uuid]
        if obj.global_uuid != uuid:
            other_id = obj.global_uuid
            del uuid2obj[uuid]
            if check_uuid:
                raise Exception(f'obj.global_uuid != uuid, {other_id},!= {uuid}')
            obj = None
        return obj
    # raise Exception(f'can not find uuid {uuid}!')
    console.warning(f'can not find uuid {uuid}!')
    return None
