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
