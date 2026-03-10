import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import bpy
import numpy as np
from bpy.types import Operator, Context
from bpy.utils import register_classes_factory

from ..model.qianyi_project import QianyiProject
from ..declarations import Operators
from ..model.pattern import Pattern
from ..utilities.node_tree import get_active_node_tree, set_active_node_tree
from ..declarations import Panels

from bpy_extras.io_utils import ImportHelper


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


class NODE_OT_qmyi_import(Operator, ImportHelper):
    """添加多边形"""
    bl_idname = Operators.Import
    bl_label = "Import file"
    # bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE', 'HIDDEN'})
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={'SKIP_SAVE', 'HIDDEN'})

    filename_ext = ".zpac;.sgar"
    filter_glob: bpy.props.StringProperty(
        default="*.zpac;*.sgar",
        options={'HIDDEN'},
    )

    @classmethod
    def poll(cls, context: Context):
        space = context.space_data
        if space and space.tree_type and space.tree_type == Panels.QianyiNodeTree:
            return True
        return False

    def execute(self, context):
        # The directory property must be set.
        if not self.directory:
            return {'CANCELLED'}

        temp_dir = tempfile.mkdtemp(prefix="qmyi_import_")
        for file in self.files:
            # Direct calls to this Operator may use unsupported file-paths. Ensure the incoming
            # files are ones that are supported.
            bpy.context.workspace.status_text_set("Importing " + filepath)
            if file.name.endswith(".zpac"):
                filepath = os.path.join(self.directory, file.name)
                with open(filepath, 'rb') as f:
                    compressed_data = f.read()
                with zipfile.ZipFile(io.BytesIO(compressed_data), 'r') as zip_file:
                    file_list = zip_file.namelist()
                    pac_name = None
                    for filename in file_list:
                        if filename.endswith('.pac'):
                            pac_name = filename
                            break
                    project_name = Path(pac_name).stem
                    pac_dir = Path(temp_dir, project_name)
                    Path.mkdir(pac_dir, exist_ok=True)
                    zip_file.extractall(pac_dir)
                    with open(Path(pac_dir, pac_name), 'rb') as f:
                        data = f.read()
                    objs = parse_marvelous_designer_map(data)

                    def parse_uint32(meta):
                        res = np.frombuffer(data[meta[1]:meta[1] + meta[2]], dtype=np.uint32)
                        if res.shape[0] == 1:
                            res = res[0]
                        return res

                    def parse_xy(meta):
                        res = np.frombuffer(data[meta[1]:meta[1] + meta[2]], dtype=np.float32)
                        if res.shape[0] > 2:
                            res = res.reshape(-1, 2)
                        return res

                    def parse_triangle_index(meta):
                        res = np.frombuffer(data[meta[1]:meta[1] + meta[2]], dtype=np.uint32).reshape(-1, 3)
                        return res

                    tree: QianyiProject = bpy.data.node_groups.new(project_name, Panels.QianyiNodeTree)
                    set_active_node_tree(context, tree)
                    md_patterns = objs["mapPatternEditor"]["mapPatternList"]["listPattern"]
                    for md_pattern in md_patterns:
                        name_meta = md_pattern["mapElement"]["qsNameUTF8"]
                        pattern_name = data[name_meta[1]:name_meta[1] + name_meta[2]].decode('utf-8')
                        pattern: Pattern = tree.patterns.add()
                        pattern.name = pattern_name

                        listPoint = md_pattern["mapShape2D"]["listPoint"]
                        listLine = md_pattern["mapShape2D"]["listLine"]
                        mesh2D = md_pattern["mapFabricShape2D"]["mapMesh2D"]

                        matrix_meta = md_pattern["mapShape2D"]["mapTransformer2D"]["m3Matrix"]
                        M = np.frombuffer(data[matrix_meta[1]:matrix_meta[1] + matrix_meta[2]],
                                          dtype=np.float32).reshape(-1, 3)
                        translate, scale, rotation = get_transform_from_matrix2d(M)

                        pattern.anchor = translate
                        # pattern.rotation = rotation

                        for point in listPoint:
                            pos = M[:2, :2].T @ parse_xy(point["v2Position"])
                            pattern.add_vertex(pos)

                        for line in listLine:
                            iLineType = line["iLineType"]
                            iLineType = np.frombuffer(data[iLineType[1]:iLineType[1] + 4], dtype=np.uint32)[0]
                            index1, index2 = parse_uint32(line["uiStartPointIndex"]), parse_uint32(
                                line["uiEndPointIndex"])
                            if "listPoint" in line:
                                lineListPoint = line["listPoint"]
                                if iLineType == 3:
                                    control1, control2 = M[:2, :2].T @ parse_xy(lineListPoint[0]["v2Position"]), M[:2, :2].T @ parse_xy(
                                        lineListPoint[1]["v2Position"])
                                    pattern.add_edge(index1, index2, "BESSEL", control1, control2, "FREE", "FREE")
                                elif iLineType == 2:
                                    edge = pattern.add_edge(index1, index2, "CUBIC_SPLINE",update=False)
                                    for p in lineListPoint:
                                        edge.add_edge_point(M[:2, :2].T @ parse_xy(p["v2Position"]))
                                    edge.update()
                            elif iLineType == 0:
                                pattern.add_edge(index1, index2)

        shutil.rmtree(temp_dir)
        context.area.tag_redraw()
        return {'FINISHED'}


register, unregister = register_classes_factory((NODE_OT_qmyi_import,))
