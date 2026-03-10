import threading
import time
import queue
import traceback
import uuid
from typing import Callable, Any, Optional, Dict, List
import sys

from utilities.console import console_print


# AI generated
class Action:
    """表示一个异步操作，可以等待结果"""

    def __init__(self, action_id: str):
        self.action_id = action_id
        self._result = None
        self._exception = None
        self._completed = False
        self._event = threading.Event()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """等待操作完成，返回是否完成"""
        if self._completed:
            return True

        if self._event.wait(timeout):
            return True
        else:
            return False

    def done(self) -> bool:
        """检查操作是否完成"""
        return self._completed

    def result(self, timeout: Optional[float] = None) -> Any:
        """获取操作结果，如果未完成则等待"""
        if not self._completed:
            if not self.wait(timeout):
                raise TimeoutError(f"Action {self.action_id} timed out")

        if self._exception:
            raise self._exception
        return self._result

    def _set_result(self, result: Any):
        """设置操作结果（内部使用）"""
        self._result = result
        self._completed = True
        self._event.set()

    def _set_exception(self, exception: Exception):
        """设置操作异常（内部使用）"""
        self._exception = exception
        self._completed = True
        self._event.set()


# AI generated
class ScheduledTask:
    """定时任务类"""

    def __init__(self, task_id: str, interval: float, func: Callable, *args, **kwargs):
        self.task_id = task_id
        self.interval = interval  # 执行间隔（秒）
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.enabled = False
        self.last_run = 0
        self.run_count = 0
        self.one_shot = False  # 是否只执行一次


CACHE_KEY = "__TaichiManager_SINGLETON__"

class TaichiManager:
    """精简的Taichi管理线程，支持异步方法调用和定时任务"""
    simulation_task_name = "simulation_task"
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, backend: str = "cuda"):
        if not hasattr(sys, CACHE_KEY):
            with cls._lock:
                if not hasattr(sys, CACHE_KEY):
                    console_print("创建taichi唯一实例中...")
                    cls._instance = super().__new__(cls)
                    cls._instance.thread = None
                    cls._instance.running = False
                    cls._instance.command_queue = queue.Queue()
                    cls._instance.backend = backend
                    cls._instance.pending_actions = {}
                    cls._instance.action_lock = threading.Lock()
                    cls._instance.taichi_initialized = False
                    cls._instance.ti = None
                    cls._instance.scheduled_tasks = {}
                    cls._instance.task_lock = threading.Lock()
                    setattr(sys, CACHE_KEY, cls._instance)
        return getattr(sys, CACHE_KEY)

    def __init__(self, backend: str = "cuda"):
        """初始化单例实例"""
        # 只在第一次初始化时设置后端
        if not hasattr(self, '_initialized') or not self._initialized:
            self.backend = backend
            self._initialized = True
            # 启动管理线程
            self.start()
            self.init()

    def start(self):
        """启动Taichi管理线程"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name="TaichiManager")
        self.thread.start()
        console_print("Taichi管理线程已启动")

    def stop(self):
        """停止Taichi管理线程"""
        if not self.running:
            return

        self.running = False
        # 发送停止命令
        self._submit_command("STOP", None)

        if self.thread:
            self.thread.join(timeout=5.0)
            if self.thread.is_alive():
                console_print("Taichi线程未正常停止")
            self.thread = None

        # 停止所有定时任务
        with self.task_lock:
            for task_id, task in self.scheduled_tasks.items():
                task.enabled = False
            self.scheduled_tasks.clear()

        console_print("Taichi管理线程已停止")

    def _run(self):
        """Taichi管理线程的主循环"""
        console_print("Taichi管理线程开始运行")

        while self.running:
            try:
                # 处理命令队列
                self._process_commands()

                # 执行定时任务
                self._execute_scheduled_tasks()

                # 短暂休眠，避免过度占用CPU
                time.sleep(0.001)  # 1ms

            except Exception as e:
                console_print(f"Taichi管理线程错误: {e}")
                console_print(traceback.format_exc())
                time.sleep(0.1)  # 出错后等待100ms

        # 清理资源
        self._cleanup()
        console_print("Taichi管理线程退出")

    def _submit_command(self, command: str, data: Any, action_id: Optional[str] = None):
        """提交命令到队列"""
        if not self.running:
            raise RuntimeError("TaichiManager已停止")
        self.command_queue.put((command, data, action_id))

    def _process_commands(self):
        """处理命令队列"""
        try:
            # 非阻塞获取命令
            while True:
                try:
                    command, data, action_id = self.command_queue.get_nowait()

                    if command == "INIT":
                        self._init_taichi(data, action_id)
                    elif command == "METHOD_CALL":
                        self._execute_method(data, action_id)
                    elif command == "ADD_TASK":
                        self._add_scheduled_task(data, action_id)
                    elif command == "REMOVE_TASK":
                        self._remove_scheduled_task(data, action_id)
                    elif command == "TOGGLE_TASK":
                        self._toggle_scheduled_task(data, action_id)
                    elif command == "STOP":
                        #  # 停止线程
                        return

                    self.command_queue.task_done()

                except queue.Empty:
                    break  # 队列为空，退出循环

        except Exception as e:
            console_print(f"处理命令错误: {e}", "ERROR")
            console_print(traceback.format_exc())

    def _execute_method(self, data, action_id):
        """执行任意方法"""
        method, args, kwargs = data
        action = self._get_action(action_id)

        if not action:
            console_print(f"未找到操作: {action_id}")
            return

        try:
            # 确保Taichi已初始化
            if not self.taichi_initialized:
                self.init().wait()

            # 执行方法
            result = method(*args, **kwargs)
            # 设置结果
            action._set_result(result)

        except Exception as e:
            console_print(f"方法执行错误: {e}")
            console_print(traceback.format_exc())
            action._set_exception(e)

        # 从待处理列表中移除
        with self.action_lock:
            if action_id in self.pending_actions:
                del self.pending_actions[action_id]

    def _get_action(self, action_id):
        """获取操作对象"""
        with self.action_lock:
            return self.pending_actions.get(action_id)

    def _init_taichi(self, backend, action_id):
        """初始化Taichi"""
        try:
            if self.taichi_initialized:
                self._cleanup_taichi()

            # 导入Taichi
            import taichi as ti

            # 根据后端选择初始化
            backend_map = {
                "gpu": ti.gpu,
                "cuda": ti.cuda,
                "vulkan": ti.vulkan,
                "opengl": ti.opengl,
                "metal": ti.metal,
                "cpu": ti.cpu,
            }

            target_backend = backend_map.get(backend, ti.cpu)

            try:
                console_print(f"尝试初始化Taichi后端: {backend}")
                ti.init(arch=target_backend, offline_cache=True, kernel_profiler=False)
                self.ti = ti
                self.taichi_initialized = True
                console_print(f"Taichi {backend}后端初始化成功")
            except Exception as e:
                console_print(f"Taichi {backend}后端初始化失败: {e}", "WARNING")
                # 回退到CPU
                ti.init(arch=ti.cpu, offline_cache=True, kernel_profiler=False)
                self.ti = ti
                self.taichi_initialized = True
                console_print("Taichi回退到CPU后端")

            # 通知操作完成
            if action_id:
                action = self._get_action(action_id)
                if action:
                    action._set_result(True)
                    with self.action_lock:
                        if action_id in self.pending_actions:
                            del self.pending_actions[action_id]

        except Exception as e:
            console_print(f"Taichi初始化失败: {e}", "ERROR")
            self.taichi_initialized = False
            self.ti = None

            # 通知操作失败
            if action_id:
                action = self._get_action(action_id)
                if action:
                    action._set_exception(e)
                    with self.action_lock:
                        if action_id in self.pending_actions:
                            del self.pending_actions[action_id]

    def _cleanup_taichi(self):
        """清理Taichi资源"""
        if self.ti:
            try:
                # Taichi没有显式的清理方法，但我们可以重置字段
                self.ti = None
                self.taichi_initialized = False
                console_print("Taichi资源已清理")
            except Exception as e:
                console_print(f"清理Taichi资源错误: {e}", "ERROR")

    def _cleanup(self):
        """清理资源"""
        self._cleanup_taichi()

        # 取消所有待处理的操作
        with self.action_lock:
            for action_id, action in self.pending_actions.items():
                action._set_exception(RuntimeError("TaichiManager已停止"))
            self.pending_actions.clear()

    # 定时任务管理方法
    def _execute_scheduled_tasks(self):
        """执行定时任务"""
        current_time = time.time()

        with self.task_lock:
            for task_id, task in list(self.scheduled_tasks.items()):
                if task.enabled and current_time - task.last_run >= task.interval:
                    try:
                        # 执行任务
                        task.func(*task.args, **task.kwargs)
                        task.last_run = current_time
                        task.run_count += 1

                        # console_print(f"定时任务 {task_id} 已执行 {task.run_count} 次")

                        # 如果是单次任务，执行后禁用
                        if task.one_shot:
                            task.enabled = False
                            # console_print(f"单次任务 {task_id} 已执行并禁用")

                    except Exception as e:
                        console_print(f"定时任务 {task_id} 执行错误: {e}", "ERROR")
                        console_print(traceback.format_exc())

    def _add_scheduled_task(self, data, action_id):
        """添加定时任务"""
        task_id, interval, func, args, kwargs, one_shot = data
        action = self._get_action(action_id)

        try:
            with self.task_lock:
                if task_id in self.scheduled_tasks:
                    raise ValueError(f"任务ID已存在: {task_id}")

                task = ScheduledTask(task_id, interval, func, *args, **kwargs)
                task.one_shot = one_shot
                self.scheduled_tasks[task_id] = task

                console_print(f"已添加定时任务: {task_id}, 间隔: {interval}秒")

                if action:
                    action._set_result(task_id)
                    with self.action_lock:
                        if action_id in self.pending_actions:
                            del self.pending_actions[action_id]

        except Exception as e:
            console_print(f"添加定时任务错误: {e}", "ERROR")
            console_print(traceback.format_exc())
            if action:
                action._set_exception(e)
                with self.action_lock:
                    if action_id in self.pending_actions:
                        del self.pending_actions[action_id]

    def _remove_scheduled_task(self, task_id, action_id):
        """移除定时任务"""
        action = self._get_action(action_id)

        try:
            with self.task_lock:
                if task_id in self.scheduled_tasks:
                    del self.scheduled_tasks[task_id]
                    console_print(f"已移除定时任务: {task_id}")
                else:
                    console_print(f"未找到定时任务: {task_id}", "WARNING")

                if action:
                    action._set_result(True)
                    with self.action_lock:
                        if action_id in self.pending_actions:
                            del self.pending_actions[action_id]

        except Exception as e:
            console_print(f"移除定时任务错误: {e}", "ERROR")
            console_print(traceback.format_exc())
            if action:
                action._set_exception(e)
                with self.action_lock:
                    if action_id in self.pending_actions:
                        del self.pending_actions[action_id]

    def _toggle_scheduled_task(self, data, action_id):
        """启用/禁用定时任务"""
        task_id, enabled = data
        action = self._get_action(action_id)

        try:
            with self.task_lock:
                if task_id in self.scheduled_tasks:
                    task = self.scheduled_tasks[task_id]
                    task.enabled = enabled

                    status = "启用" if enabled else "禁用"
                    console_print(f"已{status}定时任务: {task_id}")

                    if action:
                        action._set_result(enabled)
                        with self.action_lock:
                            if action_id in self.pending_actions:
                                del self.pending_actions[action_id]
                else:
                    raise ValueError(f"未找到定时任务: {task_id}")

        except Exception as e:
            console_print(f"切换定时任务状态错误: {e}", "ERROR")
            console_print(traceback.format_exc())
            if action:
                action._set_exception(e)
                with self.action_lock:
                    if action_id in self.pending_actions:
                        del self.pending_actions[action_id]

    # 公共API

    def init(self) -> Action:
        """初始化Taichi渲染器"""
        action_id = str(uuid.uuid4())
        action = Action(action_id)

        # 注册操作
        with self.action_lock:
            self.pending_actions[action_id] = action

        # 提交初始化命令
        self._submit_command("INIT", self.backend, action_id)

        return action

    def execute(self, method: Callable, *args, **kwargs) -> Action:
        """执行任意方法并返回Action对象"""
        action_id = str(uuid.uuid4())
        action = Action(action_id)

        # 注册操作
        with self.action_lock:
            self.pending_actions[action_id] = action

        # 提交方法调用命令
        self._submit_command("METHOD_CALL", (method, args, kwargs), action_id)

        return action

    def add_scheduled_task(self, task_id: str, interval: float, func: Callable,
                           *args, one_shot: bool = False, **kwargs) -> Action:
        """添加定时任务"""
        action_id = str(uuid.uuid4())
        action = Action(action_id)

        # 注册操作
        with self.action_lock:
            self.pending_actions[action_id] = action

        # 提交添加任务命令
        self._submit_command("ADD_TASK", (task_id, interval, func, args, kwargs, one_shot), action_id)

        return action

    def remove_scheduled_task(self, task_id: str) -> Action:
        """移除定时任务"""
        action_id = str(uuid.uuid4())
        action = Action(action_id)

        # 注册操作
        with self.action_lock:
            self.pending_actions[action_id] = action

        # 提交移除任务命令
        self._submit_command("REMOVE_TASK", task_id, action_id)

        return action

    def enable_scheduled_task(self, task_id: str) -> Action:
        """启用定时任务"""
        action_id = str(uuid.uuid4())
        action = Action(action_id)

        # 注册操作
        with self.action_lock:
            self.pending_actions[action_id] = action

        # 提交启用任务命令
        self._submit_command("TOGGLE_TASK", (task_id, True), action_id)

        return action

    def disable_scheduled_task(self, task_id: str) -> Action:
        """禁用定时任务"""
        action_id = str(uuid.uuid4())
        action = Action(action_id)

        # 注册操作
        with self.action_lock:
            self.pending_actions[action_id] = action

        # 提交禁用任务命令
        self._submit_command("TOGGLE_TASK", (task_id, False), action_id)

        return action

    def toggle_scheduled_task(self, task_id: str) -> Action:
        """切换定时任务状态（启用/禁用）"""
        action_id = str(uuid.uuid4())
        action = Action(action_id)

        # 注册操作
        with self.action_lock:
            self.pending_actions[action_id] = action

        # 获取当前状态并切换
        with self.task_lock:
            current_enabled = False
            if task_id in self.scheduled_tasks:
                current_enabled = self.scheduled_tasks[task_id].enabled

        # 提交切换任务命令
        self._submit_command("TOGGLE_TASK", (task_id, not current_enabled), action_id)

        return action

    def get_scheduled_task_info(self, task_id: str) -> Optional[Dict]:
        """获取定时任务信息"""
        with self.task_lock:
            if task_id in self.scheduled_tasks:
                task = self.scheduled_tasks[task_id]
                return {
                    'task_id': task.task_id,
                    'interval': task.interval,
                    'enabled': task.enabled,
                    'last_run': task.last_run,
                    'run_count': task.run_count,
                    'one_shot': task.one_shot
                }
        return None

    def list_scheduled_tasks(self) -> List[str]:
        """列出所有定时任务ID"""
        with self.task_lock:
            return list(self.scheduled_tasks.keys())

    def is_ready(self) -> bool:
        """检查Taichi是否已初始化"""
        return self.taichi_initialized and self.ti is not None

    def get_ti(self):
        """获取Taichi实例（仅在主线程安全）"""
        return self.ti


taichi_mgr = TaichiManager(backend="gpu")