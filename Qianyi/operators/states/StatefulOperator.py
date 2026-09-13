from typing import Any, List

from bpy.props import BoolProperty
from bpy.types import Context

from ...utilities.console import console
from .IState import IState, StateResultType


class ReturnState:
    FINISHED = {"FINISHED"}
    CANCELLED = {"CANCELLED"}


all_done = True  # global


class StateOperator:
    def setup_state_machine(self, context):
        raise NotImplementedError

    def _init(self):
        self.states: List[IState] = []  # {state_index: state_instance}
        self.transitions = {}  # {source_state: {result_type: target_state}}
        self.current_state_idx = -1
        self.current_state: IState = None
        self.return_state = ReturnState.FINISHED
        global all_done
        all_done = False

    def register_state(self, state: IState) -> IState:
        """注册状态并返回状态实例"""
        self.states.append(state)
        state.state_index = len(self.states) - 1
        return state

    def define_transition(self, source: IState,
                          target: IState, result=StateResultType.SUCCESS) -> None:
        """定义状态转移规则"""

        # 确保状态已注册
        if source not in self.states:
            self.register_state(source)
        if target not in self.states:
            self.register_state(target)

        source_id = source.state_index
        # 创建转移规则
        if source_id not in self.transitions:
            self.transitions[source_id] = {}
        self.transitions[source_id][result] = target.state_index

    def _enter_state(self, context, next_state_id: int):
        """进入新状态"""
        # 清理当前状态

        if self.current_state:
            self.current_state.on_exit(context, self)

        self.current_state = self.states[next_state_id]
        self.current_state.on_enter(context, self)
        self.current_state_idx = next_state_id
        # 更新UI
        # context.area.tag_redraw()

    def _handle_state_result(self, context, result: StateResultType) -> None:
        if result == StateResultType.CONTINUE:
            return
        transition_to = None
        if self.current_state_idx in self.transitions:
            transitions = self.transitions[self.current_state_idx]
            if transitions and result in transitions:
                transition_to = transitions[result]
        if transition_to is not None:
            if isinstance(transition_to, int):
                self._enter_state(context, transition_to)
            # context.workspace.status_text_set(
            #     f"_handle_state_result{self.current_state_idx} : {transition_to} {datetime.now()}")
            # elif callable(transition_to):
            #     transition_to(state)
        else:
            if result == StateResultType.SUCCESS:
                self.handle_success(context, self.current_state)
            elif result == StateResultType.FAILURE:
                self.handle_failure(context, self.current_state)
            global all_done
            all_done = True

    def _handle_state_trans(self, context, event):
        result = self.current_state.handle_event(context, event, self)
        if result == StateResultType.CONTINUE:
            return {"PASS_THROUGH"} if self.current_state.no_blocking else {"RUNNING_MODAL"}
        elif result == StateResultType.SUCCESS:
            self.current_state.on_succeed(context)
        self._handle_state_result(context, result)
        if all_done:
            self._end(context)
            return self.return_state
        return {"RUNNING_MODAL"}

    def invoke(self, context, event):
        global all_done
        if not all_done:
            console.warning("invoke:", "task is not yet completed")
            return {"CANCELLED"}
        self._init()
        self.setup_state_machine(context)
        if len(self.states) == 0:
            all_done = True
            # console.info(self.return_state)
            # return self.return_state # it will crash too, why?
            return {"RUNNING_MODAL"}
        self.current_state_idx = 0
        self._enter_state(context, self.current_state_idx)
        res = self._handle_state_trans(context, event)
        if res == {"PASS_THROUGH"}:  # do not pass through in invoke or blender will crash...
            res = {"RUNNING_MODAL"}
        return res

    def execute(self, context):
        self._init()
        self.setup_state_machine(context)
        if len(self.states) == 0:
            return self.return_state
        self.current_state_idx = 0
        self._enter_state(context, self.current_state_idx)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        global all_done
        if all_done:
            return self.return_state
        try:
            res = self._handle_state_trans(context, event)
        except Exception as e:
            self._end(context)
            all_done = True
            raise e

        # context.workspace.status_text_set(f"{res}")
        return res

    def handle_failure(self, context, state: IState):
        pass

    def handle_success(self, context, state: IState):
        pass

    def fini(self, context: Context):
        pass

    def _end(self, context):
        context.window.cursor_modal_restore()
        self.fini(context)
