import numpy as np
from mathutils import Vector

from ..utilities.console import console


# 这个版本由AI通过taichi版本生成。我发现，只有当控制点在10000或以上的量级时，numpy版本和taichi版本的用时才有较大的差别，一般情况下这个够用了，当点到10万量级，这个版本内存会不够，请用taichi版本
def chasing_numpy(A, b):
    """
    使用追赶法求解三对角方程组 Ax = b

    :param A: 三对角矩阵，形状(n, n)
    :param b: 右端向量，形状(n,)
    :return: 解向量x，形状(n,)
    """
    n = len(b)

    # 提取三对角元素
    a = np.zeros(n)  # 下对角线 (i=1 to n-1)
    d = np.zeros(n)  # 主对角线 (i=0 to n-1)
    c = np.zeros(n)  # 上对角线 (i=0 to n-2)

    # 提取对角线元素
    for i in range(n):
        d[i] = A[i, i]
        if i > 0:
            a[i] = A[i, i - 1]
        if i < n - 1:
            c[i] = A[i, i + 1]

    # 追赶法求解
    # 前向消元
    for i in range(1, n):
        m = a[i] / d[i - 1]
        d[i] = d[i] - m * c[i - 1]
        b[i] = b[i] - m * b[i - 1]

    # 回代
    x = np.zeros(n)
    x[n - 1] = b[n - 1] / d[n - 1]
    for i in range(n - 2, -1, -1):
        x[i] = (b[i] - c[i] * x[i + 1]) / d[i]

    return x


def cubic_spline_2d_numpy(x, y, bc0_type="natural", bc0_d=0.0, bcn_type="natural", bcn_d=0.0, sample_count=1000):
    """
    二维三次样条插值

    :param x: 一维数组，节点x坐标
    :param y: 二维数组，形状为(2, n)或(n, 2)，节点y坐标
    :param bc0_type: {"natural", "constant"}
    :param bc0_d: 开始点导数，形状为(2,)或标量
    :param bcn_type: {"natural", "constant"}
    :param bcn_d: 结束点导数，形状为(2,)或标量
    :param sample_count: 采样点数
    :return: 插值结果，形状为(2, sample_count)
    """
    # 确保y是二维数组，形状为(2, n)
    y = np.asarray(y)
    if y.shape[0] != 2:
        y = y.T  # 转置为(2, n)

    n_curves, n_points = y.shape
    n = n_points - 1  # 区间数量

    # 处理边界条件导数
    bc0_d = np.asarray(bc0_d)
    bcn_d = np.asarray(bcn_d)
    if bc0_d.ndim == 0:
        bc0_d = np.full(n_curves, bc0_d)
    if bcn_d.ndim == 0:
        bcn_d = np.full(n_curves, bcn_d)

    h = np.diff(x)  # 区间长度
    y_diff = np.diff(y, axis=1)  # y的差分
    f_diff1 = y_diff / h  # 一阶差商

    # 初始化结果数组
    m_all = np.zeros((n_curves, n_points))

    # 对每条曲线分别计算
    for curve_idx in range(n_curves):
        # 构建三对角线方程组的系数矩阵
        A_mat = np.zeros((n_points, n_points))
        b_vec = np.zeros(n_points)

        # 内部点方程
        for i in range(1, n):
            # μ_i = h_{i-1} / (h_{i-1} + h_i)
            mu = h[i - 1] / (h[i - 1] + h[i])
            # λ_i = h_i / (h_{i-1} + h_i)
            lambda_val = h[i] / (h[i - 1] + h[i])

            A_mat[i, i - 1] = mu
            A_mat[i, i] = 2
            A_mat[i, i + 1] = lambda_val

            # d_i = 6 * f[x_{i-1}, x_i, x_{i+1}]
            f_div_diff = ((y[curve_idx, i + 1] - y[curve_idx, i]) / h[i] -
                          (y[curve_idx, i] - y[curve_idx, i - 1]) / h[i - 1])
            b_vec[i] = 6 * f_div_diff / (h[i - 1] + h[i])

        # 起始边界条件
        if bc0_type == "natural":
            A_mat[0, 0] = 1
            b_vec[0] = 0
        else:  # constant (clamped)
            A_mat[0, 0] = 2
            A_mat[0, 1] = 1
            f01 = (y[curve_idx, 1] - y[curve_idx, 0]) / h[0]
            b_vec[0] = 6 * (f01 - bc0_d[curve_idx]) / h[0]

        # 结束边界条件
        if bcn_type == "natural":
            A_mat[n, n] = 1
            b_vec[n] = 0
        else:  # constant (clamped)
            A_mat[n, n - 1] = 1
            A_mat[n, n] = 2
            fn1n = (y[curve_idx, n] - y[curve_idx, n - 1]) / h[n - 1]
            b_vec[n] = 6 * (bcn_d[curve_idx] - fn1n) / h[n - 1]

        # 使用追赶法求解三对角线方程组
        m_all[curve_idx] = chasing_numpy(A_mat, b_vec)

    # 计算样条系数（使用三弯矩法的标准系数公式）
    a_coeff = y[:, :-1]  # a_i = y_i
    b_coeff = (y[:, 1:] - y[:, :-1]) / h - h * (2 * m_all[:, :-1] + m_all[:, 1:]) / 6
    c_coeff = m_all[:, :-1] / 2
    d_coeff = (m_all[:, 1:] - m_all[:, :-1]) / (6 * h)

    # 生成采样点
    x_query = np.linspace(x.min(), x.max(), sample_count)
    indices = np.searchsorted(x, x_query, side='right') - 1
    indices = np.clip(indices, 0, n - 1)

    # 初始化结果数组
    y_query = np.zeros((n_curves, sample_count))

    # 对每条曲线计算插值
    for curve_idx in range(n_curves):
        # 获取对应区间的系数
        dx = x_query - x[indices]
        idx = indices

        # 计算样条值
        y_query[curve_idx, :] = (a_coeff[curve_idx, idx] +
                                 b_coeff[curve_idx, idx] * dx +
                                 c_coeff[curve_idx, idx] * dx ** 2 +
                                 d_coeff[curve_idx, idx] * dx ** 3)

    return y_query.T


def get_handles_after_split(x_old, y_old, old_start_h, old_end_h, x_split):
    """
    计算分割后，第一条曲线的起点手柄和第二条曲线的终点手柄
    参数:
        x_old: 原节点 x 数组
        y_old: 原节点 y 数组 (2, n)
        bc0_d: 原起点导数
        bcn_d: 原终点导数
        x_split: 插入的分割点 x 坐标
    返回:
        new_start_handle: 第一条曲线的起点手柄 (2,)
        new_end_handle: 第二条曲线的终点手柄 (2,)
    """
    # 1. 计算原手柄
    # old_start_h, old_end_h = get_end_handles_from_spline(x_old, y_old, bc0_d, bcn_d)
    # 2. 判断分割点是否影响了端点所在的区间
    new_start_h = old_start_h.copy()
    new_end_h = old_end_h.copy()
    # 如果分割点在第一段区间内
    if x_old[0] < x_split < x_old[1]:
        # 新步长
        h0_new = x_split - x_old[0]
        h0_old = x_old[1] - x_old[0]
        # 按比例缩短手柄 (等价于 P0 + (h_new/3) * V0)
        ratio = float(h0_new / h0_old)
        new_start_h = Vector(y_old[0]) + ratio * (old_start_h - Vector(y_old[0]))
    # 如果分割点在最后一段区间内
    if x_old[-2] < x_split < x_old[-1]:
        # 新步长
        hn_new = x_old[-1] - x_split
        hn_old = x_old[-1] - x_old[-2]
        # 按比例缩短手柄
        ratio = float(hn_new / hn_old)
        new_end_h = Vector(y_old[-1]) + ratio * (old_end_h - Vector(y_old[-1]))
    return new_start_h, new_end_h


def get_derivatives_from_handles(x, y, start_handle, end_handle):
    """
    根据贝塞尔端点手柄位置，反算样条插值的端点导数 (bc0_d, bcn_d)
    参数:
        x: 节点 x 坐标 (n,)
        y: 节点 y 坐标 (2, n)
        start_handle: 起点右侧手柄位置 (2,)，即 P1
        end_handle: 终点左侧手柄位置 (2,)，即 P2
    返回:
        bc0_d: 起点导数 (2,)
        bcn_d: 终点导数 (2,)
    """
    y = np.asarray(y)
    # 计算首尾区间的步长
    h0 = x[1] - x[0]
    hn = x[-1] - x[-2]
    # 获取起点和终点的坐标 (P0 和 P3)
    P0 = Vector(y[0].copy())
    P3 = Vector(y[-1].copy())
    # 反推导数: V = 3 * (手柄 - 锚点) / 步长
    bc0_d = 3.0 * (Vector(start_handle) - P0) / h0
    bcn_d = 3.0 * (P3 - Vector(end_handle)) / hn
    return bc0_d, bcn_d


def compute_split_handles(x, y, t_split, start_handle=None, end_handle=None):
    """
    计算三次样条在参数 t_split 处切分时，切分点处的两个贝塞尔手柄。

    :param x: 一维数组，节点参数 t (通常为弦长累积和，长度为 n+1)
    :param y: 样条控制点/节点坐标，形状为 (2, n+1) 或 (n+1, 2)
    :param start_handle: 起点右侧手柄位置 (2,) 或 None（表示自然边界）
    :param end_handle:   终点左侧手柄位置 (2,) 或 None（表示自然边界）
    :param t_split: 切分点的参数值，必须在 (x[0], x[-1]) 内
    :return: (left_handle, right_handle)
             left_handle  - 第一段曲线在切分点的左侧手柄 (2,) np.ndarray
             right_handle - 第二段曲线在切分点的右侧手柄 (2,) np.ndarray
    """
    # 确保 y 为 (2, n+1) 形状
    y = np.asarray(y, dtype=float)
    if y.shape[0] != 2:
        y = y.T

    n_curves, n_points = y.shape  # n_curves 应为 2，n_points = n+1
    if n_curves != 2:
        raise ValueError("y 必须包含两个坐标维度 (2, n)")

    n = n_points - 1  # 区间数量
    h = np.diff(x)  # 各区间长度

    # ---------- 解析边界条件 ----------
    bc0_clamped = (start_handle is not None)
    bcn_clamped = (end_handle is not None)

    bc0_d = np.zeros(2) if bc0_clamped else None
    bcn_d = np.zeros(2) if bcn_clamped else None

    # 将手柄转为 numpy 向量以便计算
    if bc0_clamped:
        start_h = np.asarray(start_handle, dtype=float)
        # 导数计算公式：3 * (H - P0) / h0
        bc0_d = 3.0 * (start_h - y[:, 0]) / h[0]

    if bcn_clamped:
        end_h = np.asarray(end_handle, dtype=float)
        # 导数计算公式：3 * (P_n - H) / h_{n-1}
        bcn_d = 3.0 * (y[:, -1] - end_h) / h[-1]

    # ---------- 求解三弯矩方程，得到所有二阶导数 M ----------
    M_all = np.zeros((2, n_points))

    for curve_idx in range(2):
        A_mat = np.zeros((n_points, n_points))
        b_vec = np.zeros(n_points)

        # 内部点方程（i = 1 ... n-1）
        for i in range(1, n):
            mu = h[i - 1] / (h[i - 1] + h[i])
            lam = h[i] / (h[i - 1] + h[i])
            A_mat[i, i - 1] = mu
            A_mat[i, i] = 2.0
            A_mat[i, i + 1] = lam

            # 二阶差商
            f_div = ((y[curve_idx, i + 1] - y[curve_idx, i]) / h[i] -
                     (y[curve_idx, i] - y[curve_idx, i - 1]) / h[i - 1])
            b_vec[i] = 6.0 * f_div / (h[i - 1] + h[i])

        # 起点边界条件
        if bc0_clamped:
            # 固定一阶导数
            A_mat[0, 0] = 2.0
            A_mat[0, 1] = 1.0
            f01 = (y[curve_idx, 1] - y[curve_idx, 0]) / h[0]
            b_vec[0] = 6.0 * (f01 - bc0_d[curve_idx]) / h[0]
        else:
            # 自然边界 (M_0 = 0)
            A_mat[0, 0] = 1.0
            b_vec[0] = 0.0

        # 终点边界条件
        if bcn_clamped:
            # 固定一阶导数
            A_mat[n, n - 1] = 1.0
            A_mat[n, n] = 2.0
            fn1n = (y[curve_idx, n] - y[curve_idx, n - 1]) / h[n - 1]
            b_vec[n] = 6.0 * (bcn_d[curve_idx] - fn1n) / h[n - 1]
        else:
            # 自然边界 (M_n = 0)
            A_mat[n, n] = 1.0
            b_vec[n] = 0.0

        # 追赶法求解
        M_all[curve_idx] = chasing_numpy(A_mat, b_vec)

    # ---------- 确定 t_split 所在区间 ----------
    idx = np.searchsorted(x, t_split, side='right') - 1
    idx = np.clip(idx, 0, n - 1)  # 防止 t_split 刚好等于 x[-1] 时出错

    hk = h[idx]
    dt = t_split - x[idx]

    # 若 dt 接近 0 且在最后一个区间内，可切换到前一个区间（避免数值问题）
    if dt < 1e-15 and idx < n - 1:
        idx += 1
        hk = h[idx]
        dt = t_split - x[idx]

    # ---------- 计算切分点的坐标与导数 ----------
    P_split = np.zeros(2)
    deriv = np.zeros(2)

    for curve_idx in range(2):
        yk = y[curve_idx, idx]
        yk1 = y[curve_idx, idx + 1]
        Mk = M_all[curve_idx, idx]
        Mk1 = M_all[curve_idx, idx + 1]

        # 区间多项式系数
        a = yk
        b = (yk1 - yk) / hk - hk * (2.0 * Mk + Mk1) / 6.0
        c = Mk / 2.0
        d = (Mk1 - Mk) / (6.0 * hk)

        # 样条值 S(dt) 和导数 S'(dt)
        P_split[curve_idx] = a + b * dt + c * dt ** 2 + d * dt ** 3
        deriv[curve_idx] = b + 2.0 * c * dt + 3.0 * d * dt ** 2

    # ---------- 反推贝塞尔手柄 ----------
    h_left = dt
    h_right = hk - dt

    left_handle = P_split - (h_left / 3.0) * deriv
    right_handle = P_split + (h_right / 3.0) * deriv

    return left_handle, right_handle
