import ctypes
import time

import numpy as np
import bpy

from utilities.console import console_print, console
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt


def generate_pattern_mesh(pattern, points, granularity, mesh_obj):
    if len(points) < 3:
        return mesh_obj
    start_time = time.time()
    edge_points = np.array(points, dtype=np.float32)
    edge_points /= 1000
    edges = [(i, (i + 1) % len(edge_points)) for i in range(len(edge_points))]
    boundary = [np.min(edge_points, axis=0) - 0.5, np.max(edge_points, axis=0) + 0.5]
    boundary = ((boundary[0] + boundary[1]) / 2, boundary[1] - boundary[0] + 2)
    # BoundaryTree = QuadTree.BoundaryTree
    # quadtree = BoundaryTree(boundary[0][0], boundary[0][1], boundary[1][0], boundary[1][1], [edge_points],
    #                         max_depth=16, min_size=0.5)

    console_print("quadtree: ", time.time() - start_time)
    start_time = time.time()
    # point_offset = np.array((quadtree.root.xmin, quadtree.root.ymin))

    # def checker(point):
    #     return quadtree.check_inside(point + point_offset) < 0

    # sampling_points = poisson_disk_sampling(*boundary[1], granularity, (edge_points - point_offset).tolist(), checker,
    #                                         9) + point_offset
    #
    # points = np.vstack((edge_points, sampling_points[len(edge_points):]))
    next_point = np.array([((i + 1) % len(edge_points)) for i in range(len(edge_points))], dtype=np.int32)
    # sampling_points = taichi_mgr.execute(sample_points,edge_points, next_point, granularity).result()
    import Qianyi_DP as qydp
    geometry = qydp.geometry
    all_points, triangles = geometry.sample_points(edge_points, next_point, float(granularity))
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
    if mesh_obj is None:
        mesh = bpy.data.meshes.new("DistMesh2D_Mesh")
        mesh_obj = bpy.data.objects.new("DistMesh2D_Object", mesh)
        mesh_obj.rotation_euler.x = 90
    else:
        mesh = mesh_obj.data
        if mesh.shape_keys:
            old_sim_vertices = mesh_obj.qmyi_simulation_props.get_simulation_vertices()
            if old_sim_vertices is not None:
                old_pattern_vertices = mesh_obj.qmyi_simulation_props.get_pattern_vertices()
                tris = np.zeros(len(mesh.loop_triangles) * 3, dtype=np.int32)
                mesh.loop_triangles.foreach_get("vertices", tris)
                tris = tris.reshape(-1, 3)
                res_index, res_weight = geometry.find_map_weight(old_pattern_vertices, tris, all_points)
                tri_verts_idx = tris[res_index]
                selected_attrs = old_sim_vertices[tri_verts_idx]

                # 使用 einsum 进行批量乘法求和
                # 'ij,ijk->ik' 含义：
                # i: 查询点数量 M
                # j: 三个顶点 (3)
                # k: 属性维度 K
                # 对 j 维度进行相乘并求和，保留 i 和 k
                map_vertices = np.einsum('ij,ijk->ik', res_weight, selected_attrs, dtype=np.float32)


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
    # 这是 Blender Python API 的核武器，比 from_pydata 还快
    # 添加空顶点和空多边形/循环
    mesh.vertices.add(num_vertices)
    mesh.polygons.add(num_polygons)
    mesh.loops.add(num_polygons * 3)  # 三角形，所以循环数是面数 * 3

    # 填充顶点坐标
    # foreach_set 需要平铺的一维数组
    mesh.vertices.foreach_set("co", vertices_3d.ravel())
    # 填充拓扑结构
    # loop_start: 0, 3, 6, 9...
    loop_starts = np.arange(0, num_polygons * 3, 3, dtype=np.int32)
    # loop_total: 3, 3, 3, 3...
    loop_totals = np.full(num_polygons, 3, dtype=np.int32)
    # vertex_indices: 直接展平三角形数组
    loop_indices = triangles.ravel().astype(np.int32)

    mesh.polygons.foreach_set("loop_start", loop_starts)
    mesh.polygons.foreach_set("loop_total", loop_totals)
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

    # 更新网格
    mesh.update(calc_edges=True)  # 自动计算边
    if pattern.is_mirror:
        mesh_obj.scale.x = -1
    else:
        mesh_obj.scale.x = 1
    mesh_obj.lock_scale = (True, True, True)

    console_print("create_mesh: ", time.time() - start_time)

    if map_vertices is not None:
        mesh_obj.qmyi_simulation_props.set_simulation_vertices(map_vertices)

    return mesh_obj


def poisson_disk_sampling(width, height, r, points, valid_checker, k=30):
    """
    泊松圆盘采样算法
    width, height: 区域尺寸
    r: 最小间距
    k: 每个活动点的尝试次数
    """
    # 初始化网格加速结构
    cell_size = r / np.sqrt(2)
    grid_width = int(np.ceil(width / cell_size))
    grid_height = int(np.ceil(height / cell_size))
    grid = [[None] * grid_height for _ in range(grid_width)]

    # # 生成第一个点
    # points = []
    # start = (np.random.uniform(0, width), np.random.uniform(0, height))
    # points.append(start)

    # 网格坐标转换
    def grid_coords(point):
        x, y = point
        return int(x / cell_size), int(y / cell_size)

    for point in points:
        gx, gy = grid_coords(point)
        grid[gx][gy] = point

    active = list(range(len(points)))  # 活动点索引列表

    # 检查点是否有效
    def is_valid(point):
        if not (0 <= point[0] < width and 0 <= point[1] < height) or not valid_checker(point):
            return False

        gx, gy = grid_coords(point)
        # 检查周围5x5网格
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                nx, ny = gx + dx, gy + dy
                if 0 <= nx < grid_width and 0 <= ny < grid_height:
                    neighbor = grid[nx][ny]
                    if neighbor is not None:
                        dist = np.hypot(point[0] - neighbor[0], point[1] - neighbor[1])
                        if dist < r:
                            return False
        return True

    # 主循环
    while active:
        # 随机选择一个活动点
        idx = np.random.choice(active)
        point = points[idx]
        found = False

        # 尝试生成新点
        for _ in range(k):
            # 在环形区域随机采样
            angle = np.random.uniform(0, 2 * np.pi)
            radius = np.random.uniform(r, 2 * r)
            new_point = (
                point[0] + radius * np.cos(angle),
                point[1] + radius * np.sin(angle)
            )

            if is_valid(new_point):
                points.append(new_point)
                gx, gy = grid_coords(new_point)
                grid[gx][gy] = new_point
                active.append(len(points) - 1)
                found = True
                break

        # 如果未找到新点，移除当前活动点
        if not found:
            active.remove(idx)

    return np.array(points)
