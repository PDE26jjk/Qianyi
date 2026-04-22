import math
import os
import struct
import tempfile
import threading
import time

import bpy
import numpy as np

from ..model.fabric import Fabric
from ..model.pattern import Pattern
from ..utilities.console import console_print, console
from .task_manager import task_mgr


class SimulationManager:
    _instance = None
    simulation_task_name = "simulation_task"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SimulationManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.running = False
        self.run_count = 0

        # 模拟对象管理
        self.simulated_objects = []  # 所有参与模拟的对象
        self.sewings = []
        self.world_matrixs = []
        self.animation_cache = {}
        self._initialized = True
        self.need_clear_velocity = False
        self.simulator = None
        self.data_lock = threading.Lock()
        self.pending_cloth_vertices = None
        self.pending_frame_vertices = None
        self.pending_colors = None
        self.new_cloth_data_available = False
        self.new_frame_data_available = False
        print("SimulationManager 已初始化")
        if self.simulation_task_name in task_mgr.scheduled_tasks:
            task_mgr.remove_scheduled_task(self.simulation_task_name).wait()
        self.need_to_set_data = False
        task_mgr.add_scheduled_task(self.simulation_task_name, 0.001, self._run)

    def _run(self):
        if not self.running:
            return
        import Qianyi_DP as qydp
        start = time.time()
        self.simulator = qydp.simulator
        if self.need_to_set_data:
            self.simulator.input_data({'mesh_list': self.simulated_objects, 'sewings': self.sewings})
            self.need_to_set_data = False
        for i, data in enumerate(self.simulated_objects):
            if data['obj'].matrix_world != self.world_matrixs[i]:
                self.world_matrixs[i] = data['obj'].matrix_world.copy()
                self.simulator.update_world_matrix(i, self.world_matrixs[i])

        with self.data_lock:
            if self.new_frame_data_available and self.pending_cloth_vertices is not None:
                for i, vertices in self.pending_frame_vertices.items():
                    self.simulator.update_local_vertices(i, vertices)
            self.new_frame_data_available = False

            # console.info('updated',self.world_matrixs[i])
        # self.simulator.update_once()
        # self.simulator.update(0.01)
        # for i in range(2):
        self.simulator.update(0.001)
        # self.simulator.update(0.001)
        time2 = time.time() - start
        console_print("simulation: ", time2 * 1000)
        self.run_count += 1

        # start = time.time()
        with self.data_lock:
            self.pending_cloth_vertices = self.simulator.get_simulation_data().reshape(-1).copy()
            self.pending_colors = self.simulator.get_debug_colors().reshape(-1).copy()
            self.new_cloth_data_available = True

    def apply_simulation_data(self, vertices_data, debug_colors=None):
        nb_all_v = 0
        for i, data in enumerate(self.simulated_objects):
            if self.simulated_objects[i]['object_type'] > 0:
                break
            obj = self.simulated_objects[i]['obj']
            mesh = obj.data
            shape_key = mesh.shape_keys.key_blocks['QYSim']
            num_vertices = len(mesh.vertices)
            vertices_local = vertices_data[nb_all_v * 3: (nb_all_v + num_vertices) * 3]
            shape_key.points.foreach_set("co", vertices_local)
            if debug_colors is not None:
                colors = debug_colors[nb_all_v * 3: (nb_all_v + num_vertices) * 3].reshape(-1, 3)
                color_attributes = mesh.color_attributes
                color_name = 'Color'
                if color_name in color_attributes:
                    color_attribute = color_attributes[color_name]
                    colors_4d = np.zeros((colors.shape[0], 4))
                    colors_4d[:, :3] = colors
                    colors_4d[:, 3] = 1.0
                    color_attribute.data.foreach_set("color", colors_4d.ravel())
            nb_all_v += num_vertices
            mesh.update()

    def _apply_blender_data(self):
        update_time_step = 0.016
        if not self.running or not self.new_cloth_data_available:
            return update_time_step * 0.25
        vertices_data = None
        debug_colors = None
        with self.data_lock:
            if self.new_cloth_data_available:
                vertices_data = self.pending_cloth_vertices
                debug_colors = self.pending_colors
                self.new_cloth_data_available = False

        if vertices_data is not None:
            self.apply_simulation_data(vertices_data, debug_colors)
        return update_time_step

    def recode_collision_vertices(self, depsgraph):
        vertices_data = {}
        for i, item in enumerate(self.simulated_objects):
            obj = item["obj"]
            if item['object_type'] > 0 and obj.qmyi_simulation_props.vertices_updated_every_frame:
                obj_eval = obj.evaluated_get(depsgraph)
                mesh = obj_eval.data
                num_vertices = len(mesh.vertices)
                vertices_local = np.empty(num_vertices * 3, dtype=np.float32)
                mesh.vertices.foreach_get("co", vertices_local)
                vertices_data[i] = vertices_local
        return vertices_data

    def _frame_changed_post_free_simulation(self, scene, depsgraph):
        # console.info(scene.frame_current, depsgraph)
        if scene.qmyi.simulation.enable_free_simulation:
            self.stop_simulation()
            return
        if not self.running:
            return
        vertices_data = self.recode_collision_vertices(depsgraph)
        if len(vertices_data) > 0:
            with self.data_lock:
                self.pending_frame_vertices = vertices_data
                self.new_frame_data_available = True

    def setup_data(self):
        self.simulated_objects.clear()
        self.world_matrixs.clear()
        projects = set()
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and (obj.qmyi_simulation_props.is_pattern_mesh or
                                       obj.qmyi_simulation_props.participate_in_simulation):
                self._initialize_object_simulation(obj)
                if obj.qmyi_simulation_props.pattern:
                    projects.add(obj.qmyi_simulation_props.pattern.project)
        self.simulated_objects.sort(key=lambda x: x['object_type'])
        for i, item in enumerate(self.simulated_objects):
            item["obj"].qmyi_simulation_props.simulation_index = i
        self.sewings.clear()
        for p in projects:
            self.sewings.extend(p.get_sewings_for_simulation())

    def start_simulation(self):
        """开始物理模拟"""
        self.setup_data()
        if self.running:
            return True
        self.running = True
        self.need_to_set_data = True
        self.run_count = 0
        with self.data_lock:
            self.pending_cloth_vertices = None
            self.pending_frame_vertices = None
            self.pending_colors = None
            self.new_cloth_data_available = False

        task_mgr.enable_scheduled_task(self.simulation_task_name)
        if not bpy.app.timers.is_registered(self._apply_blender_data):
            bpy.app.timers.register(self._apply_blender_data, persistent=True)
        if self._frame_changed_post_free_simulation not in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.append(self._frame_changed_post_free_simulation)
        return True

    def stop_simulation(self):
        """停止物理模拟"""
        task_mgr.disable_scheduled_task(self.simulation_task_name)
        self.running = False

        if bpy.app.timers.is_registered(self._apply_blender_data):
            bpy.app.timers.unregister(self._apply_blender_data)
        if self._frame_changed_post_free_simulation in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(self._frame_changed_post_free_simulation)

        with self.data_lock:
            self.pending_cloth_vertices = None
            self.pending_colors = None
            self.new_cloth_data_available = False

    def _initialize_object_simulation(self, obj):
        """初始化对象的模拟数据"""
        if not obj or obj.type != 'MESH':
            return False
        depsgraph = bpy.context.evaluated_depsgraph_get()
        mesh: bpy.types.Mesh = obj.data
        sim_props = obj.qmyi_simulation_props
        is_cloth = sim_props.is_pattern_mesh
        num_vertices = len(mesh.vertices)
        vertices_local = np.empty(num_vertices * 3, dtype=np.float32)
        world_matrix = obj.matrix_world
        if is_cloth:
            if mesh.shape_keys is None:
                obj.shape_key_add(name='Basis')
            keys = mesh.shape_keys.key_blocks
            base_name = "QYBasis"
            shape_key = keys[base_name]
            shape_key.data.foreach_get("co", vertices_local)

            sim_name = "QYSim"
            if sim_name not in keys:
                obj.shape_key_add(name=sim_name, from_mix=False)
            keys[sim_name].value = 1.0
            keys[sim_name].relative_key = keys[base_name]
            shape_key = keys[sim_name]
            vertices_sim = np.empty(num_vertices * 3, dtype=np.float32)
            shape_key.data.foreach_get("co", vertices_sim)

        else:
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.data
            world_matrix = obj_eval.matrix_world
            normals = np.zeros(len(mesh.loop_triangles) * 3, dtype=np.float32)
            mesh.loop_triangles.foreach_get("normal", normals)
            mesh.vertices.foreach_get("co", vertices_local)

        world_matrix = np.array(world_matrix, dtype=np.float32)
        # world_matrix_inv = np.linalg.inv(world_matrix)
        edges = np.empty(len(mesh.edges) * 2, dtype=np.int32)
        mesh.edges.foreach_get("vertices", edges)

        tris = np.zeros(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", tris)

        result = {'obj': obj, 'vertices': vertices_local,
                  'edges': edges, 'triangles': tris,
                  'world_matrix': world_matrix,
                  'object_type': 0 if is_cloth else 1}
        if is_cloth:
            pattern: Pattern = sim_props.pattern
            fabric = pattern.fabric
            result['vertices_sim'] = vertices_sim
            result['mass'] = fabric.weight
            result['granularity'] = pattern.granularity
            result['thickness'] = fabric.thickness
            result['friction'] = fabric.friction
            result['stretch'] = np.array(fabric.stretch, dtype=np.float32)
            result['shear'] = np.array(fabric.shear, dtype=np.float32)
            result['bending'] = np.array(fabric.bending, dtype=np.float32)

            result['fixed_vertices'] = sim_props.get_vertex_group_weight(sim_props.fix_pin_group_name)
            result['attached_vertices'] = sim_props.get_vertex_group_weight(sim_props.attach_pin_group_name)
            # console.info(result)
        else:
            result['normals'] = normals
            result['mass'] = 1.
            # console_print(obj.simulation_props.mass, result['object_type'])
        self.simulated_objects.append(result)
        self.world_matrixs.append(world_matrix.copy())
        console_print(f"已初始化 {obj.name} 的模拟数据")
        return True

    def _frame_changed_post_animation(self, scene, depsgraph):
        if not scene.qmyi.simulation.simulation_with_animation:
            self.stop_simulation_with_animation()
            return
        if not self.running:
            return
        fps = scene.render.fps
        frame_time_step = 1.0 / fps
        console.info("frame_time_step", frame_time_step)
        vertices_data = self.recode_collision_vertices(depsgraph)
        start_time = time.time()
        for i, data in enumerate(self.simulated_objects):
            if data['obj'].matrix_world != self.world_matrixs[i]:
                self.world_matrixs[i] = data['obj'].matrix_world.copy()
                self.simulator.update_world_matrix(i, self.world_matrixs[i])  # TODO lerp
        max_update_time_step = 0.001
        update_times = max(1, math.ceil(frame_time_step / max_update_time_step))
        update_time_step = frame_time_step / update_times
        for t in range(update_times):
            if len(vertices_data) > 0:
                for i, vertices in vertices_data.items():
                    vertices_lerp = vertices
                    if i in self.pending_frame_vertices:
                        a = (t + 1) / update_times
                        vertices_lerp = self.pending_frame_vertices[i] * (1 - a) + vertices_lerp * a
                    self.simulator.update_local_vertices(i, vertices_lerp)
            self.simulator.update(update_time_step)
        self.pending_frame_vertices = vertices_data

        sim_data_flat = self.simulator.get_simulation_data().reshape(-1)
        self.apply_simulation_data(sim_data_flat)
        if scene.qmyi.simulation.record_frame_cache:
            current_frame = scene.frame_current
            self.animation_cache[current_frame] = {}
            nb_all_v = 0
            for i, data in enumerate(self.simulated_objects):
                if data['object_type'] > 0:
                    break
                obj = data['obj']
                num_vertices = len(obj.data.vertices)
                vertices_local = sim_data_flat[nb_all_v * 3: (nb_all_v + num_vertices) * 3].copy()
                nb_all_v += num_vertices

                self.animation_cache[current_frame][obj.name] = vertices_local

        console.info("frame:", scene.frame_current, "simulation: ", (time.time() - start_time) * 1000)

    def start_simulation_with_animation(self):
        self.setup_data()
        self.pending_frame_vertices = self.recode_collision_vertices(bpy.context.evaluated_depsgraph_get())
        if self.running:
            return True
        self.running = True
        self.run_count = 0
        import Qianyi_DP as qydp
        self.simulator = qydp.simulator
        self.simulator.input_data({'mesh_list': self.simulated_objects, 'sewings': self.sewings})

        if self._frame_changed_post_animation not in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.append(self._frame_changed_post_animation)

    def stop_simulation_with_animation(self):
        self.running = False
        if self._frame_changed_post_animation in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(self._frame_changed_post_animation)

    def _frame_changed_pre_play_cache(self, scene, depsgraph):
        current_frame = scene.frame_current
        if current_frame in self.animation_cache:
            frame_cache = self.animation_cache[current_frame]
            for obj_name, vertices_local in frame_cache.items():
                obj = bpy.data.objects.get(obj_name)
                if obj and obj.qmyi_simulation_props.is_pattern_mesh:
                    obj.qmyi_simulation_props.set_simulation_vertices(vertices_local.reshape(-1, 3))
                    obj.data.update()

    def start_play_cache(self):
        if self._frame_changed_pre_play_cache not in bpy.app.handlers.frame_change_pre:
            bpy.app.handlers.frame_change_pre.append(self._frame_changed_pre_play_cache)

    def stop_play_cache(self):
        if self._frame_changed_pre_play_cache in bpy.app.handlers.frame_change_pre:
            bpy.app.handlers.frame_change_pre.remove(self._frame_changed_pre_play_cache)

    def save_cache_to_pc2(self):
        if len(self.animation_cache) == 0:
            console_print("缓存中没有数据，无法导出PC2。")
            return

        sorted_frames = sorted(self.animation_cache.keys())
        start_frame = sorted_frames[0]
        end_frame = sorted_frames[-1]
        num_frames = end_frame - start_frame + 1

        self.setup_data()
        for obj_data in self.simulated_objects:
            if obj_data['object_type'] > 0:
                continue

            obj = obj_data['obj']
            # 检查该对象是否在缓存中有数据
            if obj.name not in self.animation_cache[start_frame]:
                continue

            num_vertices = len(obj.data.vertices)
            filepath = os.path.join(tempfile.gettempdir(), f"{obj.name}_sim_cache.pc2")

            try:
                with open(filepath, 'wb') as f:
                    # 写入 PC2 文件头
                    f.write(b'POINTCACHE2\0')  # 12 bytes 标识
                    f.write(struct.pack('<i', 24))  # 4 bytes 文件版本
                    f.write(struct.pack('<i', start_frame))  # 4 bytes 起始帧
                    f.write(struct.pack('<i', num_frames))  # 4 bytes 总帧数
                    f.write(struct.pack('<i', num_vertices))  # 4 bytes 顶点数

                    # 逐帧写入顶点数据
                    for frame in range(start_frame, end_frame + 1):
                        if frame in self.animation_cache and obj.name in self.animation_cache[frame]:
                            # 有缓存数据的帧，直接写入
                            verts = self.animation_cache[frame][obj.name]
                            f.write(verts.tobytes())
                        else:
                            # 如果中间有缺失帧（不正常情况），用空数据补齐以防文件错位
                            f.write(b'\x00' * (num_vertices * 3 * 4))
            except Exception as e:
                console_print(f"写入PC2文件失败: {e}")
                continue

            # 清理可能存在的旧修改器
            mod_name = "QY_MeshCache"
            if mod_name in obj.modifiers:
                obj.modifiers.remove(obj.modifiers[mod_name])

            # 添加并配置 Mesh Cache 修改器
            mod = obj.modifiers.new(name=mod_name, type='MESH_CACHE')
            mod.cache_format = 'PC2'
            mod.filepath = filepath
            mod.frame_start = start_frame
            mod.frame_end = end_frame

            # 根据你的物理引擎坐标系可能需要调整这里
            mod.forward_axis = 'POS_Y'
            mod.up_axis = 'POS_Z'
            mod.flip_axis = 'NO_AXIS'

            # 关闭 QYSim，让修改器接管
            if obj.data.shape_keys and 'QYSim' in obj.data.shape_keys.key_blocks:
                obj.data.shape_keys.key_blocks['QYSim'].value = 0.0

            console_print(f"对象 {obj.name} 的缓存已保存至 Mesh Cache 修改器")

        # 导出完成后，自动切换到修改器回放模式
        # self.stop_simulation_with_animation()
        # self.stop_play_cache()  # 确保不冲突，因为修改器自己会驱动动画


simulation_manager = SimulationManager()
