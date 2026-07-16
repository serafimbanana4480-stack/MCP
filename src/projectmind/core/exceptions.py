class ProjectMindError(Exception):
    """Base error exposed as a safe tool result."""


class GateBlocked(ProjectMindError):
    """A mandatory workflow gate did not pass."""


class SecurityViolation(ProjectMindError):
    """An operation violates the local security policy."""
