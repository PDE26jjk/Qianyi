import ctypes
import time

import numpy as np
import bpy

from ..utilities.console import console_print, console
from mathutils import Vector
from math import radians

# from mathutils.geometry import delaunay_2d_cdt

def profiling() -> bool:
    """Whether a mesh build prints what each of its phases cost.

    The Debug panel's switch, off by default: it is a diagnostic, not something
    a session pays for.
    """
    try:
        return bool(bpy.context.scene.qmyi.mesh_profile)
    except Exception:
        return False


def _mark(name, started) -> float:
    """Print one phase's cost and return the time the next phase starts at."""
    now = time.time()
    if profiling():
        console_print(f"  [mesh] {name}: {now - started:.4f}")
    return now


def triangulator_choice() -> int:
    """Which triangulator the sampler runs: the solver debug panel's setting.

    gDel2D is the mature one; gCDT is newer and faster but still unstable on
    some inputs, so anything that cannot read the setting falls back to gDel2D.
    """
    try:
        return int(bpy.context.scene.qmyi.triangulator)
    except Exception:
        return 0


def memmove(target_pointer, array) -> None:
    """Copy a numpy array over data Blender owns, without going through RNA."""
    ctypes.memmove(target_pointer, array.ctypes.data_as(ctypes.c_char_p), array.nbytes)


def generate_pattern_mesh(pattern, granularity, mesh_obj, scale_data=None):
    points = pattern.mesh_edge_points
    if len(points) < 3:
        return mesh_obj
    start_time = time.time()
    edge_points = np.array(points, dtype=np.float32)
    edge_points /= 1000
    # edges = [(i, (i + 1) % len(edge_points)) for i in range(len(edge_points))]
    # boundary = [np.min(edge_points, axis=0) - 0.5, np.max(edge_points, axis=0) + 0.5]
    # boundary = ((boundary[0] + boundary[1]) / 2, boundary[1] - boundary[0] + 2)
    # BoundaryTree = QuadTree.BoundaryTree
    # quadtree = BoundaryTree(boundary[0][0], boundary[0][1], boundary[1][0], boundary[1][1], [edge_points],
    #                         max_depth=16, min_size=0.5)

    # console_print("quadtree: ", time.time() - start_time)
    start_time = time.time()
    # point_offset = np.array((quadtree.root.xmin, quadtree.root.ymin))

    # def checker(point):
    #     return quadtree.check_inside(point + point_offset) < 0

    # sampling_points = poisson_disk_sampling(*boundary[1], granularity, (edge_points - point_offset).tolist(), checker,
    #                                         9) + point_offset
    #
    # points = np.vstack((edge_points, sampling_points[len(edge_points):]))
    # next_point = np.array([((i + 1) % len(edge_points)) for i in range(len(edge_points))], dtype=np.int32)
    # sampling_points = taichi_mgr.execute(sample_points,edge_points, next_point, granularity).result()
    import Qianyi_DP as qydp
    geometry = qydp.geometry
    is_holes = np.array((0, *[il.is_hole for il in pattern.internal_lines]), dtype=np.int32)
    # The size of each curve's sample run: the outline's first, then one per
    # internal line. Both live on the panel, because the samples do.
    curve_sizes = np.array([pattern.mesh_edge_point_outer_size,
                            *[pattern.line_sizes[index]
                              for index in range(len(pattern.internal_lines))]],
                           dtype=np.int32)
    all_points, triangles = geometry.sample_points(edge_points, pattern.mesh_edge_point_indices,
                                                   curve_sizes, is_holes, float(granularity),
                                                   triangulator=triangulator_choice())
    console_print("sample_points: ", time.time() - start_time)
    start_time = time.time()
    # all_points = np.vstack((edge_points, sampling_points))
    # constraint = np.column_stack([np.arange(next_point.size), next_point]).astype(np.int32)
    # triangles = geometry.delaunay_2d(all_points, constraint)
    # triangles = geometry.sample_points_dbg(edge_points, edge_points).reshape(-1,3)

    # result = delaunay_2d_cdt(
    #     points,  # 位置参数1: 顶点坐标
    #     edges,  # 位置参数2: 边列表
    #     [],  # 位置参数3: 面列表
    #     2,  # 位置参数4: 输出类型
    #     1e-5,  # 位置参数5: epsilon值
    #     False  # 位置参数6: 是否需要原始ID映射
    # )
    # (out_verts, out_edges, out_faces, orig_verts, orig_edges, orig_faces) = result
    # console_print("delaunay: ", time.time() - start_time)
    # start_time = time.time()
    map_vertices = None
    topo_nochanged = False
    old_vertex_group = None
    if mesh_obj is None:
        mesh = bpy.data.meshes.new("DistMesh2D_Mesh")
        mesh_obj = bpy.data.objects.new("DistMesh2D_Object", mesh)
        mesh_obj.rotation_euler.x = radians(90)
    else:
        mesh = mesh_obj.data
        sim_props = mesh_obj.qmyi_simulation_props
        if len(all_points) == len(mesh.vertices):
            topo_nochanged = True
            old_vertex_group = sim_props.get_vertex_group_weight(sim_props.fix_pin_group_name)
        if mesh.shape_keys:
            stamp = time.time()
            old_sim_vertices = sim_props.get_simulation_vertices()
            stamp = _mark("read simulation shape key", stamp)
            if old_sim_vertices is not None:
                old_pattern_vertices = sim_props.get_pattern_vertices()
                stamp = _mark("read base shape key", stamp)
                # The triangles of the mesh that is about to be replaced: the
                # ones this function wrote last time. Reading them back from
                # Blender re-tessellates the whole old mesh first, so the array
                # that was written is kept on the pattern and used again; the
                # read-back stays as the fallback for a mesh someone else built.
                stored = pattern.mesh_triangles
                if stored is not None and len(stored) == len(mesh.polygons):
                    tris = stored
                    stamp = _mark("reuse the triangles written last time", stamp)
                else:
                    tris = np.zeros(len(mesh.loop_triangles) * 3, dtype=np.int32)
                    stamp = _mark("loop_triangles buffer", stamp)
                    mesh.loop_triangles.foreach_get("vertices", tris)
                    stamp = _mark("loop_triangles read (fallback)", stamp)
                    tris = tris.reshape(-1, 3)
                res_index, res_weight = geometry.find_map_weight(old_pattern_vertices, tris, all_points,
                                                                 map_bounds=scale_data is not None)
                stamp = _mark("find_map_weight (old triangles -> new points)", stamp)
                tri_verts_idx = tris[res_index]
                selected_attrs = old_sim_vertices[tri_verts_idx]

                # 使用 einsum 进行批量乘法求和
                # 'ij,ijk->ik' 含义：
                # i: 查询点数量 M
                # j: 三个顶点 (3)
                # k: 属性维度 K
                # 对 j 维度进行相乘并求和，保留 i 和 k
                map_vertices = np.einsum('ij,ijk->ik', res_weight, selected_attrs, dtype=np.float32)
                stamp = _mark(f"mix attributes ({selected_attrs.shape[1]} values per vertex)",
                              stamp)
                if scale_data is not None:
                    scale_center, scale_factor = scale_data["center"], scale_data["factor"]
                    local_center = mesh_obj.matrix_world.inverted() @ scale_center
                    cx = np.array(local_center, dtype=np.float32)
                    map_vertices = cx + (map_vertices - cx) * scale_factor

        # The mesh is rebuilt in full every time. The point order the sampler
        # returns changes between runs, and the attributes and vertex groups on
        # this mesh are indexed by it, so keeping the old arrays would leave them
        # describing the wrong vertices: the arrays are cleared and the whole
        # mesh is written again, every run.
        mesh.clear_geometry()
    if mesh_obj.name not in bpy.context.collection.objects:
        bpy.context.collection.objects.link(mesh_obj)

    has_basis = False
    if mesh.shape_keys:
        mesh_obj.shape_key_clear()

    num_vertices = len(all_points)
    zeros = np.zeros((num_vertices, 1), dtype=np.float32)
    # 拼接成 [x, y, 0] 格式
    vertices_3d = np.hstack((all_points, zeros))

    # 2. 准备面数据 (过滤逻辑优化)

    # p_a = all_points[triangles[:, 0]]
    # p_b = all_points[triangles[:, 1]]
    # p_c = all_points[triangles[:, 2]]
    #
    # # 计算叉积绝对值
    # cross_product = np.abs((p_b[:, 0] - p_a[:, 0]) * (p_c[:, 1] - p_a[:, 1]) -
    #                        (p_b[:, 1] - p_a[:, 1]) * (p_c[:, 0] - p_a[:, 0]))

    # 过滤
    # mask = cross_product > 1e-8
    # final_triangles = triangles[mask]
    num_polygons = len(triangles)

    # 3. 批量创建几何体 (foreach_set)
    # 添加空顶点和空多边形/循环
    mesh.vertices.add(num_vertices)
    mesh.polygons.add(num_polygons)
    mesh.loops.add(num_polygons * 3)  # 三角形，所以循环数是面数 * 3

    # Positions and the polygon offsets go in with a memmove when the storage is
    # the layout this expects: the RNA writers cost about 2 ms and 5 ms at 45k
    # triangles where the copy costs a fraction of a millisecond, and the result
    # is the same data either way (checked field by field). It stays a full
    # write - every vertex, every corner - so a changed point order is written.
    vertex_stride = 0
    fast_write = False
    if num_vertices and num_polygons:
        vertex_stride = ((mesh.vertices[1].as_pointer()
                          - mesh.vertices[0].as_pointer()) // 4)
        polygon_stride = mesh.polygons[1].as_pointer() - mesh.polygons[0].as_pointer()
        fast_write = vertex_stride == 3 and polygon_stride == 4
    if fast_write:
        packed_vertices = np.zeros((num_vertices, vertex_stride), dtype=np.float32)
        packed_vertices[:, :3] = vertices_3d
        memmove(mesh.vertices[0].as_pointer(), packed_vertices)
    else:
        mesh.vertices.foreach_set("co", vertices_3d.ravel())
    # 填充拓扑结构
    # loop_start: 0, 3, 6, 9...
    loop_starts = np.arange(0, num_polygons * 3, 3, dtype=np.int32)
    # loop_total: 3, 3, 3, 3...
    loop_totals = np.full(num_polygons, 3, dtype=np.int32)
    # vertex_indices: 直接展平三角形数组
    loop_indices = triangles.ravel().astype(np.int32)

    # A mesh of triangles has loop_start = 3i and loop_total = 3 whatever the
    # point order is, so the arrays that are already there keep them.
    if fast_write:
        # Blender 4.x keeps one array of loop offsets, `count + 1` of them, and
        # reads loop_start and loop_total out of it: for triangles that array is
        # 0, 3, 6, ... 3 * count.
        memmove(mesh.polygons[0].as_pointer(),
                np.arange(0, num_polygons * 3 + 1, 3, dtype=np.int32))
    else:
        mesh.polygons.foreach_set("loop_start", loop_starts)
        mesh.polygons.foreach_set("loop_total", loop_totals)
    stamp = time.time()
    # mesh.loops.foreach_set("vertex_index", loop_indices) # Very slow!!
    # TODO Not safe!
    first_loop = mesh.loops[0]
    loop_ptr = first_loop.as_pointer()
    int_array = (ctypes.c_int * len(loop_indices))
    dest = int_array.from_address(loop_ptr)
    ctypes.memmove(dest, loop_indices.ctypes.data_as(ctypes.c_char_p),
                   len(loop_indices) * ctypes.sizeof(ctypes.c_int))
    # console_print("mesh8: ", time.time() - start_time)
    # start_time = time.time()

    stamp = _mark("write vertices + polygons + corners", stamp)
    # Kept for the next rebuild's attribute mapping (see above).
    pattern.mesh_triangles = triangles
    # 更新网格
    mesh.update(calc_edges=True)
    _mark("mesh.update(calc_edges=True)", stamp)
    stamp = time.time()
    if pattern.is_mirror:
        mesh_obj.scale.x = -1
    else:
        mesh_obj.scale.x = 1
    mesh_obj.lock_scale = (True, True, True)

    console_print("create_mesh: ", time.time() - start_time)
    _mark("sim props + vertex groups + renderer", stamp)

    sim_props = mesh_obj.qmyi_simulation_props
    if map_vertices is not None:
        sim_props.set_simulation_vertices(map_vertices)
    if topo_nochanged and old_vertex_group is not None: # todo map it
        sim_props.set_vertex_group_weight(sim_props.fix_pin_group_name, old_vertex_group)

    return mesh_obj

