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
        self._initialized = True
        self.need_clear_velocity = False
        self.simulator = None
        print("SimulationManager 已初始化")
        if self.simulation_task_name in task_mgr.scheduled_tasks:
            task_mgr.remove_scheduled_task(self.simulation_task_name).wait()
        self.need_to_set_data = False
        task_mgr.add_scheduled_task(self.simulation_task_name, 0.001, self._run)

    def _run(self):
        if not self.running:
            return
        import Qianyi_DP as qydp
        # if self.simulator is None:
        #     return
        start = time.time()
        self.simulator = qydp.simulator
        if self.need_to_set_data:
            # self.simulator.set_init_data(self.simulated_objects)
            self.simulator.input_data({'mesh_list': self.simulated_objects, 'sewings': self.sewings})
            # self.simulator.initialize_springs()
            self.need_to_set_data = False
        for i, data in enumerate(self.simulated_objects):
            if data['obj'].matrix_world != self.world_matrixs[i]:
                self.world_matrixs[i] = data['obj'].matrix_world.copy()
                self.simulator.update_world_matrix(i, self.world_matrixs[i])
                # console.info('updated',self.world_matrixs[i])
        # self.simulator.update_once()
        # self.simulator.update(0.01)
        # for i in range(2):
        self.simulator.update(0.0008)
        # self.simulator.update(0.001)
        time2 = time.time() - start
        console_print("simulation: ", time2 * 1000)
        self.run_count += 1

        if self.run_count % 1 == 0:
            # start = time.time()
            vertices_data = self.simulator.get_simulation_data().reshape(-1)
            debug_colors = self.simulator.get_debug_colors().reshape(-1)
            # console_print("copy data 1: ", (time.time() - start) * 1000)
            start = time.time()
            nb_all_v = 0
            for i, data in enumerate(self.simulated_objects):
                if self.simulated_objects[i]['object_type'] > 0:
                    break
                obj = self.simulated_objects[i]['obj']
                mesh = obj.data
                shape_key = mesh.shape_keys.key_blocks['QYSim']
                num_vertices = len(mesh.vertices)
                vertices_local = vertices_data[nb_all_v * 3: (nb_all_v + num_vertices) * 3]
                colors = debug_colors[nb_all_v * 3: (nb_all_v + num_vertices) * 3].reshape(-1, 3)
                # print(i,vertices_local)
                nb_all_v += num_vertices
                shape_key.points.foreach_set("co", vertices_local)  # TODO update it in main thread, or will crash.
                color_attributes = mesh.color_attributes
                color_name = 'Color'
                if color_name in color_attributes:
                    color_attribute = color_attributes[color_name]
                    colors_4d = np.zeros((colors.shape[0], 4))
                    colors_4d[:, :3] = colors
                    colors_4d[:, 3] = 1.0
                    color_attribute.data.foreach_set("color", colors_4d.ravel())
                mesh.update()
            # console_print("copy data 2: ", (time.time() - start) * 1000)
            # start = time.time()

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
        task_mgr.enable_scheduled_task(self.simulation_task_name)
        return True

    def stop_simulation(self):
        """停止物理模拟"""
        task_mgr.disable_scheduled_task(self.simulation_task_name)
        self.running = False

        # print("物理模拟已停止")

    def _initialize_object_simulation(self, obj):
        """初始化对象的模拟数据"""
        if not obj or obj.type != 'MESH':
            return False

        mesh: bpy.types.Mesh = obj.data
        is_cloth = obj.qmyi_simulation_props.is_pattern_mesh
        num_vertices = len(mesh.vertices)
        vertices_local = np.empty(num_vertices * 3, dtype=np.float32)
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
            normals = np.zeros(len(mesh.loop_triangles) * 3, dtype=np.float32)
            mesh.loop_triangles.foreach_get("normal", normals)
            mesh.vertices.foreach_get("co", vertices_local)

        world_matrix = obj.matrix_world
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
            pattern:Pattern = obj.qmyi_simulation_props.pattern
            fabric = pattern.fabric
            result['vertices_sim'] = vertices_sim
            result['mass'] = fabric.weight
            result['granularity'] = pattern.granularity
            result['thickness'] = fabric.thickness
            result['friction'] = fabric.friction
            result['stretch'] = np.array(fabric.stretch, dtype=np.float32)
            result['shear'] = np.array(fabric.shear, dtype=np.float32)
            result['bending'] = np.array(fabric.bending, dtype=np.float32)
            # console.info(result)
        else:
            result['normals'] = normals
            result['mass'] = 1.
            # console_print(obj.simulation_props.mass, result['object_type'])
        self.simulated_objects.append(result)
        self.world_matrixs.append(world_matrix.copy())
        console_print(f"已初始化 {obj.name} 的模拟数据")
        return True


simulation_manager = SimulationManager()
