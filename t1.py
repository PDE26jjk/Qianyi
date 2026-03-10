import taichi as ti

ti.init(arch=ti.gpu)  # 或使用 ti.init(arch=ti.cpu)

max_num_particles = 256
dt = 1e-3

# 主要改动1：变量声明方式更新
num_particles = ti.field(ti.i32, shape=())
spring_stiffness = ti.field(ti.f32, shape=())
paused = ti.field(ti.i32, shape=())
damping = ti.field(ti.f32, shape=())

particle_mass = 1
bottom_y = 0.05

# 主要改动2：矢量/矩阵声明方式更新
x = ti.Vector.field(2, dtype=ti.f32, shape=max_num_particles)
v = ti.Vector.field(2, dtype=ti.f32, shape=max_num_particles)

# 主要改动3：弹簧长度矩阵声明更新
rest_length = ti.field(ti.f32, shape=(max_num_particles, max_num_particles))

connection_radius = 0.15
gravity = ti.Vector([0, -9.8])


@ti.kernel
def substep():
    n = num_particles[None]
    for i in range(n):
        v[i] *= ti.exp(-dt * damping[None])  # 阻尼
        total_force = gravity * particle_mass

        for j in range(n):
            if rest_length[i, j] != 0:
                x_ij = x[i] - x[j]
                # 主要改动4：规范化操作更安全
                if x_ij.norm() > 1e-6:
                    total_force += -spring_stiffness[None] * (x_ij.norm() - rest_length[i, j]) * x_ij.normalized()

        v[i] += dt * total_force / particle_mass

    # 地面碰撞
    for i in range(n):
        if x[i].y < bottom_y:
            x[i].y = bottom_y
            v[i].y = 0

    # 位置更新
    for i in range(n):
        x[i] += v[i] * dt


@ti.kernel
def new_particle(pos_x: ti.f32, pos_y: ti.f32):
    new_particle_id = num_particles[None]
    x[new_particle_id] = [pos_x, pos_y]
    v[new_particle_id] = [0, 0]
    num_particles[None] += 1

    # 连接现有粒子
    for i in range(new_particle_id):
        dist = (x[new_particle_id] - x[i]).norm()
        if dist < connection_radius:
            # 双向设置弹簧长度
            rest_length[i, new_particle_id] = dist
            rest_length[new_particle_id, i] = dist


# GUI初始化
gui = ti.GUI('Mass Spring System', res=(512, 512), background_color=0xdddddd)

# 初始化参数
spring_stiffness[None] = 10000
damping[None] = 20

# 添加初始粒子
new_particle(0.3, 0.3)
new_particle(0.3, 0.4)
new_particle(0.4, 0.4)

while gui.running:
    # 主要改动5：事件处理更新
    for e in gui.get_events():
        if e.key == gui.ESCAPE:
            gui.running = False
        elif e.key == ' ':
            paused[None] = not paused[None]
        elif e.key == gui.LMB:
            new_particle(e.start_pos[0], e.start_pos[1])
        elif e.key == 'c':
            num_particles[None] = 0
            # 主要改动6：清除方法更新
            rest_length.fill(0)
        elif e.key == 's':
            spring_stiffness[None] *= 1.1 if not gui.is_pressed('Shift') else 1 / 1.1
        elif e.key == 'd':
            damping[None] *= 1.1 if not gui.is_pressed('Shift') else 1 / 1.1

    if not paused[None]:
        # 多次子步长确保稳定性
        for step in range(10):
            substep()

    particles_pos = x.to_numpy()[:num_particles[None]]
    gui.circles(particles_pos, color=0xffaa77, radius=5)

    # 绘制地面
    gui.line(begin=(0.0, bottom_y), end=(1.0, bottom_y), color=0x0, radius=1)

    # 绘制弹簧
    for i in range(num_particles[None]):
        for j in range(i + 1, num_particles[None]):
            if rest_length[i, j] != 0:
                gui.line(particles_pos[i], particles_pos[j], color=0x445566, radius=2)

    # 显示控制信息
    gui.text(f'C: clear all; Space: pause', pos=(0, 0.95))
    gui.text(f'S: Spring stiffness {spring_stiffness[None]:.1f}', pos=(0, 0.9))
    gui.text(f'D: Damping {damping[None]:.2f}', pos=(0, 0.85))

    gui.show()