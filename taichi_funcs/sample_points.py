# %%
import math
import numpy as np
import taichi as ti
from taichi_funcs.geometry import vi2, vf2

# %%
radius = ti.field(ti.f32, shape=())
one_grid_length = ti.field(ti.f32, shape=())
grid_size = ti.field(ti.i32, shape=())
max_size = ti.field(ti.i32, shape=())
n = ti.field(ti.i32, shape=())
nb_points = ti.field(ti.i32, shape=())
nb_boundary_points = ti.field(ti.i32, shape=())

max_grid_particles_size = 4


@ti.func
def grid_index(p: vf2) -> vi2:
    return ti.cast(p // one_grid_length[None], ti.i32)


@ti.func
def try_test(index: vi2, grid_status: ti.types.ndarray(ti.u8, ndim=2)):
    return ti.atomic_or(grid_status[index], ti.u8(1 << 1)) == ti.u8(0)


@ti.kernel
def fill_area(points: ti.types.ndarray(vf2, ndim=1),
              final: ti.types.ndarray(vf2, ndim=1),
              grid_status: ti.types.ndarray(ti.u8, ndim=2),
              grid_point: ti.types.ndarray(ti.i32, ndim=2),
              next_point: ti.types.ndarray(ti.i32, ndim=1)):
    for i in points:
        point = points[i]
        index = grid_index(point)
        if grid_status[index] == ti.u8(0):
            if try_test(index, grid_status):
                j = ti.atomic_add(nb_points[None], 1)
                final[j] = point
                grid_point[index] = i
                point = (point + points[next_point[i]]) * 0.5
                index = grid_index(point)
                if grid_status[index] == ti.u8(0):
                    if try_test(index, grid_status):
                        j = ti.atomic_add(nb_points[None], 1)
                        final[j] = point
                        grid_point[index] = i

    for i in range(nb_points[None]):
        point = final[i]
        index = grid_index(point)
        next_p = points[next_point[grid_point[index]]]
        d = 1 if next_p[0] - point[0] > 0 else -1
        x, y = index
        while 0 <= y + d < max_size[None]:
            y = y + d
            if grid_status[x, y] != ti.u8(0):
                break
            else:
                grid_status[x, y] = ti.u8(4)
    nb_boundary_points[None] = nb_points[None]
    for x, y in ti.ndrange(grid_size[None], grid_size[None]):
        if grid_status[x, y] == ti.u8(4):
            point = vf2([ti.random(), ti.random()])
            local_pos = (point + vf2([x, y])) * one_grid_length[None]
            j = ti.atomic_add(nb_points[None], 1)
            final[j] = local_pos


@ti.kernel
def repulsion(grid_multi_point_size: ti.types.ndarray(ti.u8, ndim=2),
              grid_multi_point: ti.types.ndarray(ti.types.vector(max_grid_particles_size, ti.i32), ndim=2),
              force: ti.types.ndarray(vf2, ndim=1),
              final: ti.types.ndarray(vf2, ndim=1),
              factor: float):
    for i, j in ti.ndrange(grid_size[None], grid_size[None]):
        grid_multi_point_size[i, j] = ti.u8(0)
    for i in range(nb_points[None]):
        point = final[i]
        index = grid_index(point)
        _id = ti.atomic_add(grid_multi_point_size[index], ti.u8(1))
        if _id < max_grid_particles_size:
            grid_multi_point[index][_id] = i
    for _i in range(nb_boundary_points[None], nb_points[None]):
        point = final[_i]
        index = grid_index(point)
        x, y = index
        r2 = radius[None] ** 2
        d = vf2([0., 0.])
        # near_size = 0
        for i in range(max(0, x - 1), min(max_size[None], x + 2)):
            for j in range(max(0, y - 1), min(max_size[None], y + 2)):
                for k in range(min(grid_multi_point_size[i, j], max_grid_particles_size)):
                    p2_i = grid_multi_point[i, j][k]
                    if p2_i == _i:
                        continue
                    p2 = final[p2_i]
                    l = point - p2
                    l2 = l.dot(l)
                    if l2 < (r2 * 0.5) + 1e-6:
                        d += l.normalized() / l2
                        # near_size += 1
        force[_i] = d

    for i in range(nb_boundary_points[None], nb_points[None]):
        # print(force[i] * radius * 0.01)
        d = force[i]
        maxd = radius[None] * factor
        if d.dot(d) > maxd ** 2:
            d = d.normalized() * maxd
        final[i] += d


@ti.kernel
def coll_valid_point(final: ti.types.ndarray(vf2, ndim=1),
                     grid_status: ti.types.ndarray(ti.u8, ndim=2),
                     valid_status: ti.types.ndarray(ti.u8, ndim=1)):
    for i in range(nb_boundary_points[None], nb_points[None]):
        if grid_status[grid_index(final[i])] == ti.u8(4):
            valid_status[i] = ti.u8(1)
        else:
            valid_status[i] = ti.u8(0)


# %%

class Data:
    def __init__(self, _radius):
        radius[None] = _radius
        self.radius = _radius
        max_size, n = self.set_radius(_radius)

        self.grid_status = ti.ndarray(ti.u8, shape=(max_size, max_size))  # 0 empty, 1 edge, 2 inside
        self.grid_point = ti.ndarray(ti.i32, shape=(max_size, max_size))
        self.final = ti.Vector.ndarray(2, ti.f32, n)

        self.grid_multi_point = ti.Vector.ndarray(max_grid_particles_size, ti.i32, shape=(max_size, max_size))
        self.grid_multi_point_size = ti.ndarray(ti.u8, shape=(max_size, max_size))
        self.force = ti.Vector.ndarray(2, ti.f32, n)
        self.valid_status = ti.ndarray(ti.u8, n)

    def set_radius(self, _radius):
        self.radius = _radius
        _one_grid_length = _radius / (2 ** 0.5)
        _grid_size = math.ceil(1 / _one_grid_length)
        _max_size = int(((_grid_size + 63) // 64) * 64)
        _n = _max_size ** 2
        radius[None] = _radius
        one_grid_length[None] = _one_grid_length
        grid_size[None] = _grid_size
        max_size[None] = _max_size
        n[None] = _n
        return _max_size, _n


data: Data = None


# d = data(0.0001)
def sample_points(boundary_points, next_point, radius, f1=0.02, t1=15, f2=0.01, t2=35):
    global data
    x_min, y_min = boundary_points.min(axis=0)
    x_max, y_max = boundary_points.max(axis=0)
    width = x_max - x_min
    height = y_max - y_min
    scale = 1.0 / (max(width, height) + radius)
    offset = np.array([x_min, y_min])
    radius_scaled = radius * scale
    if data is None or data.radius > radius_scaled:
        data = Data(radius_scaled)
    else:
        data.set_radius(radius_scaled)

    points_normalized = (boundary_points - offset + radius * 0.5) * scale
    data.grid_status.fill(0)
    nb_points[None] = 0
    fill_area(points_normalized, data.final, data.grid_status, data.grid_point, next_point)
    for i in range(t1):
        repulsion(data.grid_multi_point_size, data.grid_multi_point, data.force, data.final, f1)
    for i in range(t2):
        repulsion(data.grid_multi_point_size, data.grid_multi_point, data.force, data.final, f2)
    coll_valid_point(data.final, data.grid_status, data.valid_status)
    final_points = data.final.to_numpy()[nb_boundary_points[None]: nb_points[None]][
        data.valid_status.to_numpy()[nb_boundary_points[None]: nb_points[None]] > 0]
    return final_points / scale - radius * 0.5 + offset

# %%
# points = sample_points(boundary_points, next_point, r, 0.02, 15, 0.01, 35)
