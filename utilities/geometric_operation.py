import numpy as np


def split_polyline(points, percentage):
    """
    按百分比分割二维点链，将点链按分割点分成两部分返回。
    保留分割点在前一段的末尾，后一段的开头。

    :param points: np.ndarray, shape (N, 2)
    :param percentage: float, 0.0 ~ 1.0
    :return: (part1, part2) 二维点链的两个部分
    """
    points = np.asarray(points)
    if len(points) < 2:
        return points.copy(), points.copy()

    diffs = np.diff(points, axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    cum_lengths = np.cumsum(seg_lengths)
    total_length = cum_lengths[-1]

    if total_length == 0:
        return points.copy(), points.copy()

    percentage = np.clip(percentage, 0.0, 1.0)
    target = total_length * percentage
    scans = np.r_[0, cum_lengths]

    # 找到目标长度所在线段的右端点索引
    right_i = np.searchsorted(scans, target, side='right')
    right_i = min(max(right_i, 1), len(points) - 1)
    left_i = right_i - 1

    # 计算分割点
    seg_len = scans[right_i] - scans[left_i]
    ratio = (target - scans[left_i]) / seg_len if seg_len > 0 else 0.0
    split_pt = points[left_i] * (1 - ratio) + points[right_i] * ratio

    # 构建两部分点链，处理刚好命中顶点(ratio==0)时避免重复添加同一个点
    if ratio == 0:
        part1 = points[:right_i]  # 不包含 split_pt 对应的顶点，因为在 part2 开头
        part2 = np.vstack([[split_pt], points[right_i:]])
    else:
        part1 = np.vstack([points[:right_i], [split_pt]])
        part2 = np.vstack([[split_pt], points[right_i:]])

    return part1, part2

def resample_polyline(points, segments, endpoint=False):
    """
    对二维点列进行基于距离的多段重采样。

    参数:
        points: numpy array, 形状为 (n, 2)，原始点列。
        segments: list of tuples, 形如 [(0, 10), (0.3, 20)]，
                  表示起点的归一化位置和该段的采样点数。

    返回:
        resampled_points: numpy array, 重采样后的点列 (m, 2)。
    """
    points = np.asarray(points)

    # 1. 计算原始点列的累积距离并归一化到 [0, 1]
    diffs = np.diff(points, axis=0)
    dists = np.linalg.norm(diffs, axis=1)
    cum_dists = np.insert(np.cumsum(dists), 0, 0)

    # 防止除以 0（例如传入的所有点都在同一个位置）
    total_length = cum_dists[-1]
    if total_length == 0:
        return points

    t_orig = cum_dists / total_length

    # 2. 根据 segments 构造采样的目标参数 t
    t_queries = []
    for i in range(len(segments)):
        start_t, num_points = segments[i]

        # 确定当前段的结束 t 值（如果是最后一段，则默认延伸到 1.0）
        # 生成当前段的 t 值。
        if i < len(segments) - 1:
            end_t = segments[i + 1][0]
            # endpoint=False 保证了“包含初始点，不包含末尾点”，从而不会与下一段重叠
            t_segment = np.linspace(start_t, end_t, num_points, endpoint=False)
        else:
            end_t = 1.0
            t_segment = np.linspace(start_t, end_t, num_points, endpoint=endpoint)

        t_queries.append(t_segment)

    t_queries = np.concatenate(t_queries)

    # 3. 分别对 X 和 Y 坐标进行一维线性插值
    x_resampled = np.interp(t_queries, t_orig, points[:, 0])
    y_resampled = np.interp(t_queries, t_orig, points[:, 1])

    return np.column_stack((x_resampled, y_resampled))

def forward_diff_bezier(q, n):
    """
    计算单条2D贝塞尔曲线的离散点（完全向量化实现）

    参数:
        q: (4, 2) 形状的数组，包含曲线的控制点
        n: 迭代次数（分段数）

    返回:
        points: (n+1, 2) 形状的数组，曲线上的点
    """
    assert q.shape == (4, 2), f"Expected control points shape (4,2), got {q.shape}"
    if n == 0:
        return np.array([q[0]])

    # 计算差分变量
    rt0 = q[0]
    rt1 = 3.0 * (q[1] - q[0]) / n
    rt2 = 3.0 * (q[0] - 2.0 * q[1] + q[2]) / (n * n)
    rt3 = (q[3] - q[0] + 3.0 * (q[1] - q[2])) / (n * n * n)

    # 重组迭代变量
    q0 = rt0
    q1 = rt1 + rt2 + rt3
    q2 = 2 * rt2 + 6 * rt3
    q3 = 6 * rt3

    # 创建索引数组
    k = np.arange(n + 1)

    # 使用累加和公式计算点位置
    term1 = k[:, None] * q1
    term2 = (k * (k - 1) / 2)[:, None] * q2
    term3 = (k * (k - 1) * (k - 2) / 6)[:, None] * q3

    return q0 + term1 + term2 + term3
