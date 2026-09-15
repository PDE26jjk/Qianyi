import traceback

from .utilities.console import Console, console

temp_draw_manager: 'TempDrawManager' = None

temp_data = []
uuid2obj = {}

# Renderers (gizmos, viewport batches) need a GPU context. The data path - the
# payload the simulation engine receives, the scene capture package - must also
# work in a background Blender session, where creating a shader is not allowed.
# A caller that only needs data sets this to False; every renderer construction
# and batch update on the data path is guarded by it.
renderers_enabled = True


def get_obj_by_uuid(uuid, check_uuid=True, check_valid=False):
    if uuid in uuid2obj:
        obj = uuid2obj[uuid]
        if obj is not None:
            # Liveness + identity check in one property read instead of
            # `path_from_id()`.
            #
            # The map can still hold a Python wrapper whose Blender data is
            # gone (the UI, an operator or user code in a notebook deleted it),
            # and touching removed data must not take Blender down. Measured on
            # Blender 4.5.6, for the ways our data disappears:
            #   - a datablock (Object, NodeTree) was removed: any property read
            #     raises ReferenceError;
            #   - an item was removed from a collection (patterns.remove,
            #     edges.remove): the wrapper reads back as a default, so
            #     `global_uuid` is -1 - or, when the collection shifted another
            #     item onto it, simply a different uuid;
            #   - nothing was removed: the uuid still matches.
            # So one guarded uuid read answers both "still alive" and "still
            # this object", which is what the identity check below needs
            # anyway. It costs 0.2 us per call for every object, while
            # `path_from_id()` costs 0.003 ms to 1.1 ms depending on the object
            # (the pattern editor calls this lookup dozens of times per
            # redraw) and it missed the shifted-item case, where it still
            # returned a path for a wrapper that now points at a different
            # edge.
            try:
                current_uuid = obj.global_uuid
            except Exception:
                # Removed datablock: any access raises.
                current_uuid = None
            if current_uuid is None:
                del uuid2obj[uuid]
                if check_valid:
                    raise Exception(f'{uuid} is invalid!')
                else:
                    console.warning(f'{uuid} is invalid!')
                return None
            if current_uuid != uuid:
                other_id = current_uuid
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
