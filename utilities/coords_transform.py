import math

import mathutils


def region3view_coord(context, pos):
    region = context.region.view3d
    x, y = region.region_to_view(pos[0], pos[1])
    return x, y

def region2view_coord(context, pos):
    region = context.region.view2d
    # ui_scale = context.preferences.system.ui_scale
    x, y = region.region_to_view(pos[0], pos[1])
    return x, y


def create_2d_matrix(scale=(1, 1), rotation=0, offset=(0, 0)):
    sx, sy = scale
    tx, ty = offset
    c, s = math.cos(rotation), math.sin(rotation)

    matrix = mathutils.Matrix((
        (sx * c, -sy * s, 0, tx),
        (sx * s, sy * c, 0, ty),
        (0, 0, 0, 0),
        (0, 0, 0, 1)
    ))

    return matrix


def create_2d_matrix_invert(scale=(1, 1), rotation=0, offset=(0, 0)):
    sx, sy = scale
    tx, ty = offset
    c, s = math.cos(rotation), math.sin(rotation)

    if abs(sx) < 1e-6:
        sx = 1e-6
    if abs(sy) < 1e-6:
        sy = 1e-6

    inv_sx = 1.0 / sx
    inv_sy = 1.0 / sy

    a = c * inv_sx
    b = s * inv_sx
    c_ = -s * inv_sy
    d = c * inv_sy

    inv_tx = -(a * tx + c_ * ty)
    inv_ty = -(b * tx + d * ty)

    return mathutils.Matrix((
        (a, c_, 0, inv_tx),
        (b, d, 0, inv_ty),
        (0, 0, 1, 0),
        (0, 0, 0, 1)
    ))