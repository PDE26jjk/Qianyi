import numpy as np


def parse_marvelous_designer_map(data: bytes, map_offset=0, map_length=-1):
    objects = []
    offset = map_offset
    if map_length == -1:
        map_length = len(data)
    map_end = map_offset + map_length

    while offset < map_end:
        # 读取对象属性数量
        if offset >= map_end:
            break

        num_properties = data[offset]
        offset += 1

        if num_properties == 0:
            break

        name_lengths = np.frombuffer(data[offset:offset + num_properties], dtype=np.ubyte)
        offset += num_properties
        types = np.frombuffer(data[offset:offset + num_properties], dtype=np.ubyte)
        offset += num_properties
        value_lengths = np.frombuffer(data[offset:offset + num_properties * 4], dtype=np.uint32)
        offset += num_properties * 4

        properties_metadata = {}
        for i in range(num_properties):
            name_length = int(name_lengths[i])
            # if offset + name_length > len(data):
            #     break

            property_name = data[offset:offset + name_length].decode('gbk', errors='ignore')
            offset += name_length

            value_length = value_lengths[i]
            value_offset = offset
            offset += value_length  # 跳过属性值

            type_id = types[i]
            # global_offset = value_offset + map_offset
            if type_id == 22:
                properties_metadata[property_name] = parse_marvelous_designer_map(
                    data, value_offset, value_length)
            elif type_id == 20:
                list_offset = value_offset
                list_count = np.frombuffer(data[list_offset:list_offset + 4], dtype=np.uint32)[0]
                if list_count > 0:
                    list_offset += 4
                    list_item_type_id = data[list_offset]
                    list_offset += 1
                    if list_item_type_id == 22:
                        list_item_lengths = np.frombuffer(data[list_offset:list_offset + list_count * 4],
                                                          dtype=np.uint32)
                        list_offset += list_count * 4
                        l = []
                        for j in range(list_count):
                            l.append(parse_marvelous_designer_map(data, list_offset, list_item_lengths[j]))
                            list_offset += list_item_lengths[j]
                        properties_metadata[property_name] = l
                    else:
                        properties_metadata[property_name] = (int(types[i]), int(value_offset), int(value_length))
            else:
                properties_metadata[property_name] = (int(types[i]), int(value_offset), int(value_length))
                # properties_metadata[property_name] = (types[i], value_offset, value_length)
            # properties_metadata[property_name] = int(value_length)

        objects.append(properties_metadata)
        break

    if len(objects) >= 1:
        return objects[0]
    return None


def get_transform_from_matrix2d(M):
    translate = M[2, 0], M[2, 1]
    A = M[:2, :2].T
    U, S, Vt = np.linalg.svd(A)
    rotation_matrix = U @ Vt
    scale = S
    det = np.linalg.det(rotation_matrix)

    if det < 0:
        rotation_matrix = U @ np.diag([-1, 1]) @ Vt
        scale[0] *= -1  # 将反射分配给x轴缩放
    rotation = np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
    return translate, scale, rotation

