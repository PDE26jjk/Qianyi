import traceback

from utilities.console import Console, console

temp_draw_manager: 'TempDrawManager' = None

temp_data = []
uuid2obj = {}


def get_obj_by_uuid(uuid, check_uuid=True, check_valid=False):
    if uuid in uuid2obj:
        obj = uuid2obj[uuid]
        if obj is not None:
            try:
                obj.path_from_id()
            except Exception as e:
                del uuid2obj[uuid]
                if check_valid:
                    raise Exception(f'{uuid} is invalid!')
                else:
                    console.warning(f'{uuid} is invalid!')
                return None
        if obj.global_uuid != uuid:
            other_id = obj.global_uuid
            del uuid2obj[uuid]
            if check_uuid:
                raise Exception(f'obj.global_uuid != uuid, {other_id},!= {uuid}')
            else:
                console.warning(f'obj.global_uuid != uuid, {other_id},!= {uuid}')
            obj = None
        return obj

    stack = traceback.extract_stack()
    caller_stack = stack
    stack_info = "trace：\n"
    for i, frame_info in enumerate(caller_stack[-10:]):
        stack_info += f"  {i + 1}. {frame_info.filename}, line: {frame_info.lineno},function {frame_info.name}\n"

    console.warning(f'can not find uuid {uuid}!')
    console.warning(stack_info)
    return None
