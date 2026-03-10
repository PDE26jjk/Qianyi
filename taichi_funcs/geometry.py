import taichi as ti

vf3 = ti.math.vec3
vf2 = ti.math.vec2
vi2 = ti.math.ivec2
vi3 = ti.math.ivec3
mf4 = ti.math.mat4
mf3 = ti.math.mat3
mf2 = ti.math.mat2
i32 = ti.types.i32
u32 = ti.types.u32
f32 = ti.types.f32

eps = 1e-6


@ti.func
def triangle_aabb(v0: vf3, v1: vf3, v2: vf3):
    return ti.Vector([min(v0[0], v1[0], v2[0]), min(v0[1], v1[1], v2[1]), min(v0[2], v1[2], v2[2])]), \
        ti.Vector([max(v0[0], v1[0], v2[0]), max(v0[1], v1[1], v2[1]), max(v0[2], v1[2], v2[2])])


@ti.func
def point_in_box(v, _min, _max, padding):
    _min -= padding
    _max += padding
    return (_min[0] < v[0] < _max[0]) and (_min[1] < v[1] < _max[1]) and (_min[2] < v[2] < _max[2])


@ti.func
def triangle_is_valid(e1, e2):
    return e1.cross(e2).normalized() < eps


@ti.real_func
def point_in_triangle2d(x: vf3, e1: vf3, e2: vf3) -> bool:
    res = False
    cross = e1[0] * e2[1] - e1[1] * e2[0]

    if abs(cross) > eps:
        d = 1.0 / cross
        u = (x[0] * e2[1] - x[1] * e2[0]) * d
        v = (x[1] * e1[0] - x[0] * e1[1]) * d
        res = u > eps and v > eps and u + v < 1.0 - eps

    return res


@ti.real_func
def point_in_triangle2d_out(x: vf3, e1: vf3, e2: vf3) -> bool:
    res = False
    cross = e1[0] * e2[1] - e1[1] * e2[0]

    if abs(cross) > eps:
        d = 1.0 / cross
        u = (x[0] * e2[1] - x[1] * e2[0]) * d
        v = (x[1] * e1[0] - x[0] * e1[1]) * d
        res = u > -eps and v > -eps and u + v < 1.0 + eps

    return res


@ti.real_func
def triangle2d_uv(x: vf3, e1: vf3, e2: vf3) -> (bool, f32, f32):
    res = False
    cross = e1[0] * e2[1] - e1[1] * e2[0]
    u, v = 0., 0.
    if abs(cross) > eps:
        d = 1.0 / cross
        u = (x[0] * e2[1] - x[1] * e2[0]) * d
        v = (x[1] * e1[0] - x[0] * e1[1]) * d
        res = u > eps and v > eps and u + v < 1.0 - eps

    return res, u, v


@ti.func
def point_in_triangle_same_plane(x, e1, e2):
    """判断点是否严格在3D三角形内部（假设点与三角形共面）"""
    res = False

    # 首先尝试使用XY平面投影
    cross = e1[0] * e2[1] - e1[1] * e2[0]

    if abs(cross) > eps:
        # XY平面投影有效
        d = 1.0 / cross
        u = (x[0] * e2[1] - x[1] * e2[0]) * d
        v = (x[1] * e1[0] - x[0] * e1[1]) * d
        res = u > eps and v > eps and u + v < 1.0 - eps
    else:
        # XY平面投影退化，尝试XZ平面
        cross = e1[0] * e2[2] - e1[2] * e2[0]
        if abs(cross) > eps:
            d = 1.0 / cross
            u = (x[0] * e2[2] - x[2] * e2[0]) * d
            v = (x[2] * e1[0] - x[0] * e1[2]) * d
            res = u > eps and v > eps and u + v < 1.0 - eps
        else:
            # XY和XZ平面都退化，使用YZ平面
            cross = e1[1] * e2[2] - e1[2] * e2[1]
            if abs(cross) > eps:
                d = 1.0 / cross
                u = (x[1] * e2[2] - x[2] * e2[1]) * d
                v = (x[2] * e1[1] - x[1] * e1[2]) * d
                res = u > eps and v > eps and u + v < 1.0 - eps
            else:
                # 所有平面投影都退化，三角形是退化的
                res = False

    return res


@ti.func
def make_matrix_XZ(X, Z):
    Y = Z.cross(X)
    return ti.Matrix([[X[0], X[1], X[2]], [Y[0], Y[1], Y[2]], [Z[0], Z[1], Z[2]]])


@ti.func
def to_space3(M, v0, v1, v2, origin):
    v0 -= origin
    v1 -= origin
    v2 -= origin
    points = ti.Matrix([[v0[0], v1[0], v2[0]], [v0[1], v1[1], v2[1]], [v0[2], v1[2], v2[2]]])
    points = M @ points
    return ti.Vector([points[0, 0], points[1, 0], points[2, 0]]), \
        ti.Vector([points[0, 1], points[1, 1], points[2, 1]]), \
        ti.Vector([points[0, 2], points[1, 2], points[2, 2]])


@ti.real_func
def segment_intersect2d(p1: vf3, l1: vf3, p2: vf3, l2: vf3) -> f32:
    cross = l1[1] * l2[0] - l2[1] * l1[0]
    res = -1.0
    if abs(cross) > eps:
        d = 1.0 / cross
        dp = p1 - p2
        t1 = (dp[0] * l2[1] - dp[1] * l2[0]) * d
        t2 = (dp[0] * l1[1] - dp[1] * l1[0]) * d
        if eps < t1 < 1 - eps and eps < t2 < 1 - eps:
            res = t1
            # print(res)
    return res


@ti.real_func
def segment_triangle_intersect2d(p1: vf3, p2: vf3, v0: vf3, v1: vf3, v2: vf3) -> bool:
    l1 = p2 - p1
    res = True
    if not segment_intersect2d(p1, l1, v0, v1 - v0) > 0:
        if not segment_intersect2d(p1, l1, v0, v2 - v0) > 0:
            if not segment_intersect2d(p1, l1, v1, v2 - v1) > 0:
                res = False
    # if res:
    #     print("!!")
    return res


@ti.real_func
def interceptXY(v0: vf3, v1: vf3) -> vf3:
    res = v0
    e1 = v1 - v0
    if abs(e1[2]) > eps:
        t = -v0[2] / (e1[2])
        res = v0 + t * e1
    return res


@ti.real_func
def check_triangle(M1: mf3, origin: vf3, v1: vf3, v2: vf3, n1: vf3, _v0: vf3, _v1: vf3, _v2: vf3) -> (bool, bool, vf2):
    v0 = vf3([0.0, 0.0, 0.0])
    ins_uv = vf2([0.0, 0.0])
    edge_ins = False
    res = False
    for _ in range(1):
        _e1, _e2 = _v1 - _v0, _v2 - _v0
        n2 = _e1.cross(_e2)
        _area_sq = n2.dot(n2)
        # check area > 0
        if not _area_sq > eps:
            break

        n2 = n2.normalized()
        overlap = False
        _v0, _v1, _v2 = to_space3(M1, _v0, _v1, _v2, origin)

        # parallel
        if abs(n1.dot(n2)) > 1 - eps:
            if abs(_v0[2]) > eps:
                # parallel in different plane
                break
                # in same plane
            # check overlap
            overlap = True
            if not segment_triangle_intersect2d(v0, v1, _v0, _v1, _v2):
                if not segment_triangle_intersect2d(v0, v2, _v0, _v1, _v2):
                    if not segment_triangle_intersect2d(v1, v2, _v0, _v1, _v2):
                        overlap = False
            # in case 3 edge are overlap or small inside big
            if not overlap:
                if point_in_triangle2d((_v0 + _v1 + v2) / 3.0, v1, v2):
                    overlap = True
        if overlap:
            res = True
            ins_uv = vf2([0, 0])
            break

        # check if all points in same side
        sign = int(_v0[2] > eps) + (_v1[2] > eps) + (_v2[2] > eps)
        if sign == 0 or sign == 3:
            break

        # always set _v0 to different side
        ins_v = 0  # intercept point index
        if sign == 1:
            ins_v = (int(_v1[2] > 0) * 1) | (_v2[2] > 0) * 2
        else:
            ins_v = (int(_v1[2] <= 0) * 1) | (_v2[2] <= 0) * 2
        if ins_v == 1:
            _v0, _v1 = _v1, _v0
        elif ins_v == 2:
            _v0, _v2 = _v2, _v0

        ins1 = interceptXY(_v0, _v1)
        ins2 = interceptXY(_v0, _v2)
        inc_point = (ins1 + ins2) * 0.5

        l2 = ins2 - ins1
        t = segment_intersect2d(v0, v1, ins1, l2)
        if t > 0.:
            inc_point = v1 * t
        else:
            t = segment_intersect2d(v0, v2, ins1, l2)
            if t > 0.:
                inc_point = v2 * t
            else:
                l1 = v2 - v1
                t = segment_intersect2d(v1, l1, ins1, l2)
                if t > 0.:
                    inc_point = v1 + l1 * t
        if t > 0.:
            edge_ins = True

        res, u, v = triangle2d_uv(inc_point, v1, v2)
        ins_uv = vf2([u, v])

        # depth = 0.0
        # if ins_v == 1:
        #     depth = -min(_v1[2], _v2[2])
        # else:
        #     depth = -_v0[2]
        # out = depth
        res = True
        break
    return res, edge_ins, ins_uv


@ti.real_func
def check_on_arc(v0: vf2, v1: vf2, p: vf2, c: vf2) -> bool:
    a = v0 - c
    b = v1 - c
    p_vec = p - c

    cross_ab = a.cross(b)  # a × b
    cross_ap = a.cross(p_vec)  # a × p
    cross_pb = p_vec.cross(b)  # p × b

    if cross_ab > 0:  # 逆时针方向，a→b的劣弧
        # 点p应该在a的逆时针侧和b的顺时针侧
        return cross_ap >= 0 and cross_pb >= 0
    else:  # 顺时针方向，a→b的劣弧
        # 点p应该在a的顺时针侧和b的逆时针侧
        return cross_ap <= 0 and cross_pb <= 0


@ti.func
def cross_mat(e):
    return ti.Matrix([[0., -e[2], e[1]],
                      [e[2], 0., -e[0]],
                      [-e[1], e[0], 0.]])


@ti.real_func
def get_theta_dpk(p0: vf3, p1: vf3, p2: vf3, p3: vf3) -> (vf3, vf3, vf3, vf3, f32):
    p01, p02, p32, p31, e = p1 - p0, p2 - p0, p2 - p3, p1 - p3, p2 - p1
    n0, n1 = p01.cross(p02), p32.cross(p31)
    n0_norm, n1_norm = n0.norm(), n1.norm()
    n0_, n1_, e_ = n0 / n0_norm, n1 / n1_norm, e.normalized()
    cos_theta = n0_.dot(n1_)
    sin_theta = n0_.cross(n1_).dot(e_)
    theta = ti.atan2(sin_theta, cos_theta)

    I = ti.Matrix.diag(3, 1.0)
    n0_dn0 = (I - n0_.outer_product(n0_)) / n0_norm
    n1_dn1 = (I - n1_.outer_product(n1_)) / n1_norm
    e_Tn0x = - n0_.cross(e_)
    e_Tn1x = - n1_.cross(e_)

    # p1
    n0_dpk = n0_dn0 @ cross_mat(-p02)
    n1_dpk = n1_dn1 @ cross_mat(p32)
    sin_dpk = e_Tn0x @ n1_dpk - e_Tn1x @ n0_dpk
    cos_dpk = n1_ @ n0_dpk + n0_ @ n1_dpk
    theta_dp1 = sin_dpk * cos_theta - cos_dpk * sin_theta
    # p2
    n0_dpk = n0_dn0 @ cross_mat(p01)
    n1_dpk = n1_dn1 @ cross_mat(-p31)
    sin_dpk = e_Tn0x @ n1_dpk - e_Tn1x @ n0_dpk
    cos_dpk = n1_ @ n0_dpk + n0_ @ n1_dpk
    theta_dp2 = sin_dpk * cos_theta - cos_dpk * sin_theta
    # p0
    n0_dpk = n0_dn0 @ cross_mat(e)
    sin_dpk = - e_Tn1x @ n0_dpk
    cos_dpk = n1_ @ n0_dpk
    theta_dp0 = sin_dpk * cos_theta - cos_dpk * sin_theta
    # p3
    n1_dpk = n1_dn1 @ cross_mat(-e)
    sin_dpk = e_Tn0x @ n1_dpk
    cos_dpk = n0_ @ n1_dpk
    theta_dp3 = sin_dpk * cos_theta - cos_dpk * sin_theta
    return theta_dp0, theta_dp1, theta_dp2, theta_dp3, theta
