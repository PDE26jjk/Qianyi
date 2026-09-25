"""A state machine with nothing to do: it ends the run at the first event."""

from .IState import IState, StateResultType


class RefuseState(IState):
    """End the run as a failure before it does anything.

    `StateOperator.invoke` answers a machine that registered no state with
    RUNNING_MODAL and no modal handler, which leaves the editor waiting for an
    operator that can never finish - a tool that finds nothing to work on is
    better off registering this state and letting the first event end the run.
    The reason belongs in the log, not in a popup: the user can see that a tool
    pointed at empty space did nothing.
    """

    @property
    def state_id(self):
        return "refuse the run"

    def handle_event(self, context, event, operator):
        return StateResultType.FAILURE
