import math

import numpy
import numpy as np
# import matplotlib.pyplot as plt
# import matplotlib.patches as patches
from enum import Enum
from collections import defaultdict


class NodeStatus(Enum):
    """节点状态枚举"""
    UNKNOWN = 0
    INSIDE = 1
    OUTSIDE = 2
    BOUNDARY = 3


class QuadTreeNode:
    """四叉树节点类"""

    def __init__(self, tree: "QuadTree", x, y, width, height, depth=0, max_depth=8, min_size=10):
        """
        初始化四叉树节点
        :param x: 节点中心x坐标
        :param y: 节点中心y坐标
        :param width: 节点宽度
        :param height: 节点高度
        :param depth: 当前深度
        :param max_depth: 最大深度
        :param min_size: 最小尺寸
        """
        self.tree = tree
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.depth = depth
        self.max_depth = max_depth
        self.min_size = min_size
        self.has_data = False

        # 边界框
        self.xmin = x - width / 2
        self.ymin = y - height / 2
        self.xmax = x + width / 2
        self.ymax = y + height / 2

        # 节点状态
        self.status = NodeStatus.UNKNOWN

        # 存储的元素ID集合
        self.elements = set()

        # 子节点
        self.children = []

    def contains_element(self, element_bbox):
        """检查元素是否与节点相交"""
        exmin, eymin, exmax, eymax = element_bbox

        # 检查元素是否完全在节点外
        if exmax < self.xmin or exmin > self.xmax:
            return False
        if eymax < self.ymin or eymin > self.ymax:
            return False

        return True

    def subdivide(self):
        """细分节点"""
        if self.depth >= self.max_depth:
            return False
        if self.width < self.min_size or self.height < self.min_size:
            return False

        # 计算子节点参数
        half_width = self.width / 4
        half_height = self.height / 4

        # 创建四个子节点
        self.children = [
            QuadTreeNode(self.tree, self.x - half_width, self.y - half_height,
                         self.width / 2, self.height / 2,
                         self.depth + 1, self.max_depth, self.min_size),
            QuadTreeNode(self.tree, self.x + half_width, self.y - half_height,
                         self.width / 2, self.height / 2,
                         self.depth + 1, self.max_depth, self.min_size),
            QuadTreeNode(self.tree, self.x - half_width, self.y + half_height,
                         self.width / 2, self.height / 2,
                         self.depth + 1, self.max_depth, self.min_size),
            QuadTreeNode(self.tree, self.x + half_width, self.y + half_height,
                         self.width / 2, self.height / 2,
                         self.depth + 1, self.max_depth, self.min_size)
        ]

        # 将当前元素重新分配到子节点
        for element_id in list(self.elements):
            self.remove_element_not_recursive(element_id)
            self.tree.add_element(self.tree.element_data[element_id])

        return True

    def add_element(self, element_id, element_bbox):
        """添加元素到节点"""
        # 检查元素是否与节点相交
        if not self.contains_element(element_bbox):
            return False

        self.has_data = True
        # 如果是叶子节点且未细分，尝试细分
        if not self.children:
            if self.subdivide():
                # 细分后重新尝试添加
                for child in self.children:
                    child.add_element(element_id, element_bbox)
                return True

        # 如果有子节点，添加到所有相交的子节点
        if self.children:
            added = False
            for child in self.children:
                if child.contains_element(element_bbox):
                    child.add_element(element_id, element_bbox)
                    added = True
            return added

        # 添加到当前节点
        self.elements.add(element_id)
        self.tree.add_node_to_element(element_id, self)
        return True

    def remove_element_not_recursive(self, element_id):
        self.elements.remove(element_id)
        if len(self.elements) == 0:
            self.has_data = False

    # def remove_element(self, element_id):
    #     """从节点移除元素"""
    #     # 如果有子节点，递归移除
    #     if self.children:
    #         for child in self.children:
    #             child.remove_element(element_id)
    #         return
    #
    #     # 从当前节点移除
    #     if element_id in self.elements:
    #         self.elements.remove(element_id)
    #         self.tree.remove_node_from_element(element_id, self)
    def nearest_neighbor(self, point, max_distance=float('inf')):
        """查找最近邻点"""
        best = None
        best_dist = max_distance

        # 如果是叶子节点，检查所有点
        if not self.children:
            for e in self.elements:
                exmin, eymin, exmax, eymax = self.tree.get_element_bbox(e)
                p = ((exmin + exmax) * 0.5, (eymin + eymax) * 0.5)
                dist = math.sqrt((p[0] - point[0]) ** 2 + (p[1] - point[1]) ** 2)
                if dist < best_dist:
                    best = e
                    best_dist = dist
            return best, best_dist

        # 确定查询子节点的顺序（距离优先）
        px, py = point
        children_order = []
        for child in self.children:
            if not child.has_data:
                continue
            cx, cy = child.x, child.y
            dist = math.sqrt((cx - px) ** 2 + (cy - py) ** 2)
            children_order.append((dist, child))

        children_order.sort(key=lambda x: x[0])

        # 按顺序查询子节点
        for _, child in children_order:
            # 如果当前最佳距离小于到子节点的距离，跳过
            if best_dist < child.xmin - px or best_dist < px - child.xmax:
                continue
            if best_dist < child.ymin - py or best_dist < py - child.ymax:
                continue

            candidate, cand_dist = child.nearest_neighbor(point, best_dist)
            if cand_dist < best_dist:
                best = candidate
                best_dist = cand_dist

        return best, best_dist


class QuadTree:
    """四叉树管理类"""

    def __init__(self, x, y, width, height, element_bbox_callback, max_depth=8, min_size=10, rootType=QuadTreeNode):
        self.root = rootType(self, x, y, width, height, max_depth=max_depth, min_size=min_size)
        self.root.tree = self  # 让节点可以访问树

        self.element_bbox_callback = element_bbox_callback

        # 元素到节点的链表索引
        self.element_to_nodes = []  # element_id -> [node1, node2, ...]
        self.element_data = []

        # 空闲元素ID列表
        self.free_ids = []
        self.next_id = 0

    def get_next_id(self):
        """获取下一个可用的元素ID"""
        if self.free_ids:
            return self.free_ids.pop()
        self.next_id += 1
        return self.next_id - 1

    def add_element(self, element_data):
        """
        添加元素到四叉树
        :param element_type: 元素类型标识
        :param element_data: 元素数据
        :return: 元素ID
        """
        element_id = self.get_next_id()

        # 扩展数组存储元素数据
        if element_id >= len(self.element_to_nodes):
            # 扩展数组
            new_size = max(element_id + 1, len(self.element_to_nodes) * 2)
            self._resize_arrays(new_size)

        # 初始化链表
        if element_id >= len(self.element_to_nodes):
            self.element_to_nodes.extend([[] for _ in range(element_id - len(self.element_to_nodes) + 1)])

        self.element_data[element_id] = element_data
        # 获取元素包围盒
        element_bbox = self.get_element_bbox(element_id)

        # 添加到根节点
        self.root.add_element(element_id, element_bbox)
        return element_id

    def _resize_arrays(self, new_size):
        """调整数组大小"""
        # 扩展数据数组
        if len(self.element_data) < new_size:
            self.element_data.extend([None] * (new_size - len(self.element_data)))

    def get_element_bbox(self, element_id):
        """获取元素的包围盒"""
        return self.element_bbox_callback(self.element_data[element_id])

    def add_node_to_element(self, element_id, node):
        """添加节点到元素的链表"""
        if element_id < len(self.element_to_nodes):
            if node not in self.element_to_nodes[element_id]:
                self.element_to_nodes[element_id].append(node)

    def remove_node_from_element(self, element_id, node):
        """从元素的链表中移除节点"""
        if element_id < len(self.element_to_nodes):
            if node in self.element_to_nodes[element_id]:
                self.element_to_nodes[element_id].remove(node)

    def remove_element(self, element_id):
        if self.element_to_nodes[element_id]:
            for node in self.element_to_nodes[element_id]:
                node.remove_element_not_recursive(element_id)
            self.element_to_nodes[element_id] = []

    # def remove_element(self, element_id):
    #     """从四叉树移除元素"""
    #     if element_id < len(self.element_data) and self.element_data[element_id] is not None:
    #         # 从所有节点中移除
    #         self.root.remove_element(element_id)
    #
    #         # 标记为可用
    #         self.element_data[element_id] = None
    #         self.free_ids.append(element_id)
    #
    #         # 清空链表
    #         if element_id < len(self.element_to_nodes):
    #             self.element_to_nodes[element_id] = []

    def query_point(self, point):
        """查询包含点的节点"""
        px, py = point
        return self._query_point_recursive(self.root, px, py)

    def _query_point_recursive(self, node, px, py):
        """递归查询包含点的节点"""
        if not (node.xmin <= px <= node.xmax and node.ymin <= py <= node.ymax):
            return None

        if not node.children:
            return node
        # 使用位运算计算子节点索引
        index = 0
        if px > node.x:
            index |= 1  # 设置最低位（x方向）
        if py > node.y:
            index |= 2  # 设置次低位（y方向）

        result = self._query_point_recursive(node.children[index], px, py)
        if result:
            return result

        return node

    def query_elements(self, point):
        """查询包含点的元素"""
        node = self.query_point(point)
        if not node:
            return set()

        # 收集所有相关元素
        return node.elements

    def nearest_neighbor(self, point, max_distance=float('inf')):
        """查找最近邻点"""
        return self.root.nearest_neighbor(point, max_distance)

    def draw(self, ax, draw_elements=True):
        """绘制四叉树"""
        self._draw_recursive(ax, self.root, draw_elements)

        # 设置绘图范围
        ax.set_xlim(self.root.xmin - 0.1 * self.root.width,
                    self.root.xmax + 0.1 * self.root.width)
        ax.set_ylim(self.root.ymin - 0.1 * self.root.height,
                    self.root.ymax + 0.1 * self.root.height)
        ax.set_aspect('equal')
        ax.set_title('QuadTree Visualization')
        ax.grid(True)

    def _draw_recursive(self, ax, node, draw_elements):
        import matplotlib.patches as patches
        """递归绘制节点"""
        # 绘制节点边界
        color_map = {
            NodeStatus.UNKNOWN: "gray",
            NodeStatus.INSIDE: "green",
            NodeStatus.OUTSIDE: "red",
            NodeStatus.BOUNDARY: "blue"
        }
        color = color_map.get(node.status, "black")

        rect = patches.Rectangle(
            (node.xmin, node.ymin), node.width, node.height,
            linewidth=1, edgecolor=color, facecolor='none', alpha=0.5
        )
        ax.add_patch(rect)

        # 绘制子节点
        for child in node.children:
            self._draw_recursive(ax, child, draw_elements)

        # 绘制元素
        if draw_elements:
            for element_id in node.elements:
                element_data = self.element_data[element_id]
                if element_data is None:
                    continue

                # 使用回调函数绘制元素
                draw_callback = getattr(element_data, "draw", None)
                if callable(draw_callback):
                    draw_callback(ax)
                else:
                    # 默认绘制方式
                    bbox = self.get_element_bbox(element_id)
                    xmin, ymin, xmax, ymax = bbox
                    rect = patches.Rectangle(
                        (xmin, ymin), xmax - xmin, ymax - ymin,
                        linewidth=1, edgecolor='purple', facecolor='none', alpha=0.3
                    )
                    ax.add_patch(rect)

        if not node.children:
            status_text = {
                NodeStatus.OUTSIDE: "out",
                NodeStatus.INSIDE: "in",
                NodeStatus.BOUNDARY: "edge"
            }.get(node.status, "?")
            ax.text(node.x, node.y, status_text,
                    ha='center', va='center', fontsize=8, fontweight='bold')


# 自定义元素类示例
class CustomElement:
    def __init__(self, points):
        self.points = points

    def get_bbox(self):
        """计算元素包围盒"""
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return min(xs), min(ys), max(xs), max(ys)

    def draw(self, ax):
        """绘制元素"""
        points = self.points
        if len(points) == 2:  # 线段
            ax.plot([points[0][0], points[1][0]], [points[0][1], points[1][1]], 'b-', linewidth=1)
        elif len(points) == 3:  # 三角形
            ax.plot([points[0][0], points[1][0], points[2][0], points[0][0]],
                    [points[0][1], points[1][1], points[2][1], points[0][1]], 'g-', linewidth=1)
        else:  # 多边形
            xs = [p[0] for p in points] + [points[0][0]]
            ys = [p[1] for p in points] + [points[0][1]]
            ax.plot(xs, ys, 'm-', linewidth=1)

    def __str__(self):
        print(self.points)


class BoundaryTree(QuadTree):
    def __init__(self, x, y, width, height, pointsList, max_depth=8, min_size=10):
        super().__init__(x, y, width, height, lambda self: self.get_bbox(), max_depth, min_size)
        for points in pointsList:
            for i in range(points.shape[0]):
                next_i = (i + 1) % points.shape[0]
                self.add_element(CustomElement([points[i], points[next_i]]))
        self._mark_region_recursive(self.root)

    def _mark_region_recursive(self, node):
        node.status = NodeStatus.BOUNDARY
        """递归标记节点状态"""
        if node.children:
            for child in node.children:
                self._mark_region_recursive(child)
            return

        # 叶子节点处理
        if not node.elements:
            # 使用最近边判断节点中心是否在点链内
            if self._point_in_polygon((node.x, node.y)):
                node.status = NodeStatus.INSIDE
            else:
                node.status = NodeStatus.OUTSIDE

    def _point_in_polygon(self, point):
        """使用最近边判断点是否在多边形内"""
        px, py = point

        # 找到最近的边中点
        idx, _ = self.nearest_neighbor((px, py))
        # print(self.nearest_neighbor((px, py)))
        # print(node.elements)
        if idx is None:
            return False
        return self._check_distance(idx, px, py) > 0
        # 获取最近的边

    def _check_distance(self, idx, px, py):
        p1, p2 = self.element_data[idx].points
        x1, y1 = p1
        x2, y2 = p2

        # 计算点到边的向量
        edge_vec = np.array([x2 - x1, y2 - y1])
        point_vec = np.array([px - x1, py - y1])

        # 计算垂直向量
        normal = np.array([-edge_vec[1], edge_vec[0]])

        # 归一化
        normal = normal / np.linalg.norm(normal)

        # 计算点到边的距离
        distance = np.dot(point_vec, normal)

        # 对于逆时针多边形，点在内部时距离为负
        return distance

    def check_inside(self, point):
        node = self.query_point(point)
        if node is None:
            return 999
        if node.status == NodeStatus.INSIDE:
            return -999
        elif node.status == NodeStatus.OUTSIDE or not node.elements:
            return 999
        idx, _ = node.nearest_neighbor(point)

        return -self._check_distance(idx, *point)


class TriangleTree(QuadTree):
    def __init__(self, x, y, width, height, max_depth=8, min_size=10):
        super().__init__(x, y, width, height, None, max_depth, min_size)
        center = np.asarray([x, y])
        radius = max(width, height) * 10000
        self.points = [center + radius * np.array((-1, -1)),
                       center + radius * np.array((+1, -1)),
                       center + radius * np.array((+1, +1)),
                       center + radius * np.array((-1, +1))]
        self.triangles = {}
        self.circles = {}

        T1 = (0, 1, 3)
        T2 = (2, 3, 1)
        self.triangles[T1] = [T2, None, None, 0]
        self.triangles[T2] = [T1, None, None, 1]

        self.add_triangle_to_tree(T1)
        self.add_triangle_to_tree(T2)

    def get_element_bbox(self, element_id):
        points = [self.points[idx] for idx in self.element_data[element_id]]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return min(xs), min(ys), max(xs), max(ys)

    def add_triangle_to_tree(self, tri):
        idx = self.add_element(tri)
        self.triangles[tri][3] = idx
        self.circles[tri] = self.circumcenter(tri)

    def circumcenter(self, tri):
        """Compute circumcenter and circumradius of a triangle in 2D.
        Uses an extension of the method described here:
        http://www.ics.uci.edu/~eppstein/junkyard/circumcenter.html
        """
        pts = np.asarray([self.points[v] for v in tri])
        pts2 = np.dot(pts, pts.T)
        A = np.bmat([[2 * pts2, [[1],
                                 [1],
                                 [1]]],
                     [[[1, 1, 1, 0]]]])

        b = np.hstack((np.sum(pts * pts, axis=1), [1]))
        x = np.linalg.solve(A, b)
        bary_coords = x[:-1]
        center = np.dot(bary_coords, pts)

        # radius = np.linalg.norm(pts[0] - center) # euclidean distance
        radius = np.sum(np.square(pts[0] - center))  # squared distance

        return (center, radius)

    def inCircleFast(self, tri, p):
        """Check if point p is inside of precomputed circumcircle of tri.
        """
        if tri is None:
            return False
        center, radius = self.circles[tri]
        return np.sum(np.square(center - p)) <= radius

    @staticmethod
    def point_in_triangle(p, tri):
        """
        :param p: 待检测点 (x, y)
        :param tri: 三角形顶点 (a, b, c)
        :return: True如果在三角形内，否则False
        """
        a, b, c = tri

        # 计算叉积
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        # 计算三个方向叉积
        d1 = cross(a, b, p)
        d2 = cross(b, c, p)
        d3 = cross(c, a, p)

        # 检查是否同侧（逆时针三角形）
        return (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0)

    @staticmethod
    def point_in_triangle_approx(p, tri):
        """
        近似点包含检测（快速但不精确）
        :param p: 待检测点
        :param tri: 三角形顶点
        :return: 近似结果
        """
        a, b, c = tri

        # 计算重心坐标（近似）
        denom = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        u = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / denom
        v = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / denom

        # 快速检查
        return u >= -0.001 and v >= -0.001 and (u + v) <= 1.001

    def add_point(self, p):
        p = np.asarray(p)
        self.points.append(p)
        idx = len(self.points) - 1

        # Search the triangle(s) whose circumcircle contains p
        node = self.query_point(p)
        if node is None:
            print("out of boundary!")
            return

        bad_triangles = []

        for T in [self.element_data[tri_idx] for tri_idx in node.elements]:
            if self.inCircleFast(T, p):
                bad_triangles.append(T)
                # pts = np.asarray([self.points[v] for v in T])
                # if self.point_in_triangle_approx(p, pts):
                #     break
        # Find the CCW boundary (star shape) of the bad triangles,
        # expressed as a list of edges (point pairs) and the opposite
        # triangle to each edge.
        boundary = []
        if not bad_triangles:
            print("something wrong!")
            return

        # Choose a "random" triangle and edge
        T = bad_triangles[0]
        for t in bad_triangles:
            pts = np.asarray([self.points[v] for v in t])
            if self.point_in_triangle_approx(p, pts):
                T = t
                break

        edge = 0
        to_delete = set()
        to_delete.add(T)
        # get the opposite triangle of this edge
        while True:
            # Check if edge of triangle T is on the boundary...
            # if opposite triangle of this edge is external to the list
            tri_op = self.triangles[T][edge]
            if tri_op not in bad_triangles:
                # if tri_op in self.triangles and self.inCircleFast(tri_op, p):
                #     bad_triangles.append(tri_op)
                #     continue
                # Insert edge and external triangle into boundary list
                boundary.append((T[(edge + 1) % 3], T[(edge - 1) % 3], tri_op))
                to_delete.add(T)
                # Move to next CCW edge in this triangle
                edge = (edge + 1) % 3

                # Check if boundary is a closed loop
                if boundary[0][0] == boundary[-1][1]:
                    break
            else:
                # Move to next CCW edge in opposite triangle
                edge = (self.triangles[tri_op].index(T) + 1) % 3
                T = tri_op

        # Remove triangles too near of point p of our solution
        # print("to delete: ", to_delete)
        for T in to_delete:
            self.remove_element(self.triangles[T][3])
            # for tri in self.triangles[T][:3]:
            #     if tri:
            #         tri_op = self.triangles[tri]
            #         if T in tri_op:
            #             tri_op[tri_op.index(T)] = None
            del self.triangles[T]
            del self.circles[T]

        # print(self.triangles)
        # Retriangle the hole left by bad_triangles
        new_triangles = []
        for (e0, e1, tri_op) in boundary:
            # Create a new triangle using point p and edge extremes
            T = (idx, e0, e1)

            # Store circumcenter and circumradius of the triangle
            self.circles[T] = self.circumcenter(T)

            # Set opposite triangle of the edge as neighbour of T
            tri = [tri_op, None, None, -1]
            self.triangles[T] = tri
            self.add_triangle_to_tree(T)

            # Try to set T as neighbour of the opposite triangle
            if tri_op and tri_op in self.triangles:
                # search the neighbour of tri_op that use edge (e1, e0)
                for i, neigh in enumerate(self.triangles[tri_op][:3]):
                    if neigh:
                        if e1 in neigh and e0 in neigh:
                            # change link to use our new triangle
                            self.triangles[tri_op][i] = T

            # Add triangle to a temporal list
            new_triangles.append(T)

        # Link the new triangles each another
        # print( "boundary",boundary)
        N = len(new_triangles)
        for i, T in enumerate(new_triangles):
            self.triangles[T][1] = new_triangles[(i + 1) % N]  # next
            self.triangles[T][2] = new_triangles[(i - 1) % N]  # previous
        # print(self.triangles)
        return
        for T in self.triangles:
            for tri in self.triangles[T][:3]:
                if tri:
                    if tri not in self.triangles:
                        print("!!!!!!!!!!!", tri, T, self.triangles[T])
                    tri_op = self.triangles[tri]
                    if T not in tri_op:
                        print("???????????", T,self.triangles[T], tri,self.triangles[tri])

    def exportTriangles(self):
        """Export the current list of Delaunay triangles
        """
        # Filter out triangles with any vertex in the extended BBox
        return [(a - 4, b - 4, c - 4)
                for (a, b, c) in self.triangles if a > 3 and b > 3 and c > 3]
# 用例：创建四叉树并添加元素
# 创建四叉树

# def generate_circle_boundary(center, radius, num_points):
#     """生成圆形边界点"""
#     angles = np.linspace(0, 2 * np.pi, num_points, endpoint=False)
#     x = center[0] + radius * np.cos(angles)
#     y = center[1] + radius * np.sin(angles)
#     return np.column_stack((x, y))
#

# vertices = np.array([
#     [0, 0],
#     [1, 0],
#     [1.5, 1],
#     [1, 2],
#     [0, 2],
#     [-0.5, 1],
# ]) * 2 - 0.1
#
# center = np.array([0, 0])
# radius = 4.8
# num_boundary_points = 50
# boundary_points = generate_circle_boundary(center, radius, num_boundary_points)
# boundary_points2 = generate_circle_boundary(center, radius * .5, num_boundary_points)[::-1]
#
# quadtree = BoundaryTree(0, 0, 10, 10, [boundary_points, boundary_points2], max_depth=16, min_size=0.5)
# 绘制四叉树
# fig, ax = plt.subplots(figsize=(10, 10))
# quadtree.draw(ax, draw_elements=True)
