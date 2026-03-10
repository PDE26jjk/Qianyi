import numpy as np


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
