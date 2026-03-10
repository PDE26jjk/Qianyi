import numpy as np


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



