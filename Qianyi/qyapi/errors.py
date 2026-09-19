"""The error type the script surface raises.

Kept in its own module so the surface package and its submodules can both
import it without a cycle.
"""


class QyapiError(RuntimeError):
    """An entry point could not do its work.

    ``message`` is one sentence the caller can act on; ``details`` are the
    follow-up lines (names, counts, the next call to make). Nothing is shown as
    a dialog: the caller is a script, and a dialog would block a session that
    has no user in front of it.
    """

    def __init__(self, message, details=()):
        super().__init__(message)
        self.details = tuple(str(line) for line in (details or ()))

    def as_dict(self):
        return {"error": str(self), "details": list(self.details)}
