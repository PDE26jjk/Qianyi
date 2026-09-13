import taichi as ti
import numpy as np


# 数值分析(第5版) (李庆扬, 王能超, 易大义)
# 2.8 三次样条插值, 7.4.3 追赶法

@ti.kernel
def chasing(Input: ti.types.ndarray(), Output: ti.types.ndarray()):
    """
    :param Input:  {a},{b},{c},{f}
    :param Output: {beta} {y/x}
    """
    N = Input.shape[1]
    # 处理第一个元素
    # beta[0] = c0 / b0
    Output[0, 0] = Input[2, 0] / Input[1, 0]
    # y0 = f0 / b0
    Output[1, 0] = Input[3, 0] / Input[1, 0]

    ti.loop_config(serialize=True)
    # 前向消元（追过程）
    for i in range(1, N):
        denominator = Input[1, i] - Input[0, i] * Output[0, i - 1]
        Output[0, i] = Input[2, i] / denominator  # βi = ci/(bi - ai*β_{i-1})
        Output[1, i] = (Input[3, i] - Input[0, i] * Output[1, i - 1]) / denominator

    # 回代（赶过程）
    # 最后一个元素已经是解
    for _ in range(1, N):
        i = N - _ - 1
        Output[1, i] -= Output[0, i] * Output[1, i + 1]


def cubic_spline(x, y, bc0_type="natural", bc0_d=0.0, bcn_type="natural", bcn_d=0.0, sample_count=10000):
    """
    :param x: 节点x坐标
    :param y: 节点y坐标
    :param bc0_type: {"natural", "constant"} 边界条件类型
    :param bc0_d: constant时的开始点二阶导数
    :param bcn_type: {"natural", "constant"} 边界条件类型
    :param bcn_d: constant时的结束点二阶导数
    :param sample_count: 采样点数量
    :return: 样条插值结果
    """
    n = len(x) - 1  # 区间数量
    h = np.diff(x)  # 区间长度

    # 构建三弯矩方程组
    # 方程形式: μ_i * M_{i-1} + 2M_i + λ_i * M_{i+1} = d_i
    Input = np.zeros((4, n + 1), dtype=np.float32)

    # 计算系数
    for i in range(1, n):
        # μ_i = h_{i-1} / (h_{i-1} + h_i)
        Input[0, i] = h[i - 1] / (h[i - 1] + h[i])
        # λ_i = h_i / (h_{i-1} + h_i) = 1 - μ_i
        Input[2, i] = h[i] / (h[i - 1] + h[i])
        # 主对角线系数为2
        Input[1, i] = 2.0

        # d_i = 6 * f[x_{i-1}, x_i, x_{i+1}]
        #     = 6 * ((y_{i+1} - y_i)/h_i - (y_i - y_{i-1})/h_{i-1}) / (h_{i-1} + h_i)
        f_div_diff = ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
        Input[3, i] = 6 * f_div_diff / (h[i - 1] + h[i])

        # 处理左边界条件
    if bc0_type == "natural":
        # 自然边界条件：M_0 = 0
        Input[1, 0] = 1.0
        Input[2, 0] = 0.0
        Input[3, 0] = 0.0
    elif bc0_type == "constant":
        # 固支边界条件：已知一阶导数
        # 方程: 2M_0 + M_1 = 6/h_0 * (f[x_0, x_1] - y'_0)
        Input[1, 0] = 2.0
        Input[2, 0] = 1.0
        f01 = (y[1] - y[0]) / h[0]  # f[x_0, x_1]
        Input[3, 0] = 6.0 * (f01 - bc0_d) / h[0]

    # 处理右边界条件
    if bcn_type == "natural":
        # 自然边界条件：M_n = 0
        Input[0, n] = 0.0
        Input[1, n] = 1.0
        Input[3, n] = 0.0
    elif bcn_type == "constant":
        # 固支边界条件：已知一阶导数
        # 方程: M_{n-1} + 2M_n = 6/h_{n-1} * (y'_n - f[x_{n-1}, x_n])
        Input[0, n] = 1.0
        Input[1, n] = 2.0
        fn1n = (y[n] - y[n - 1]) / h[n - 1]  # f[x_{n-1}, x_n]
        Input[3, n] = 6.0 * (bcn_d - fn1n) / h[n - 1]

    # 使用追赶法求解三弯矩方程组
    Input_ti = ti.ndarray(ti.float32, shape=(4, n + 1))
    Input_ti.from_numpy(Input)
    Output_ti = ti.ndarray(ti.float32, (2, n + 1))

    chasing(Input_ti, Output_ti)
    M = Output_ti.to_numpy()[1, :]  # 二阶导数M

    # 计算样条系数
    # 在每个区间[x_i, x_{i+1}]上，样条函数为：
    # S_i(x) = a_i + b_i(x-x_i) + c_i(x-x_i)^2 + d_i(x-x_i)^3
    a_coeff = y[:-1]  # a_i = y_i
    b_coeff = (y[1:] - y[:-1]) / h - h * (2 * M[:-1] + M[1:]) / 6  # b_i
    c_coeff = M[:-1] / 2  # c_i = M_i / 2
    d_coeff = (M[1:] - M[:-1]) / (6 * h)  # d_i = (M_{i+1} - M_i) / (6h)

    spline_coeffs = np.vstack([a_coeff, b_coeff, c_coeff, d_coeff])

    # 生成采样点
    x_query = np.linspace(min(x), max(x), sample_count)
    indices = np.searchsorted(x, x_query, side='right') - 1
    indices = np.clip(indices, 0, n - 1)

    # 获取对应区间的系数
    a = spline_coeffs[0, indices]
    b = spline_coeffs[1, indices]
    c = spline_coeffs[2, indices]
    d = spline_coeffs[3, indices]

    # 计算相对位置
    dx = x_query - x[indices]

    # 计算样条值
    y_query = a + b * dx + c * dx ** 2 + d * dx ** 3
    return y_query
