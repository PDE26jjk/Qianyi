from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional

from typing import Optional, Dict, Any, Tuple, Callable
from enum import Enum


# ======================
# � 状态结果类型定义
# ======================

class StateResultType(Enum):
    """状态执行结果类型"""
    CONTINUE = 0  # 继续当前状态
    SUCCESS = 1  # 成功完成
    FAILURE = 2  # 失败需要处理


class IState(ABC):
    """状态接口基类"""

    def __init__(self):
        self.state_index = -1,
        self.succeed_cb = []
        self.data_change_cb = []

    @property
    @abstractmethod
    def state_id(self) -> str:
        """状态的唯一标识符"""
        pass

    def on_enter(self, context, operator):
        """进入状态时调用"""
        pass

    @abstractmethod
    def handle_event(
            self,
            context,
            event,
            operator
    ) -> StateResultType:
        """处理事件，返回状态转换指令"""
        pass

    def on_exit(self, context, operator):
        """退出状态时调用"""
        pass

    def on_data_change(self, context):
        """should be call in handle_event"""
        for cb in self.data_change_cb:
            if callable(cb):
                cb(self, context)

    def on_succeed(self, context):
        """ call by operator when handle_event return succeed"""
        for cb in self.succeed_cb:
            if callable(cb):
                cb(self, context)
