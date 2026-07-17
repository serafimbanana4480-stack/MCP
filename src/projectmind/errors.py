"""Domain errors shared by CLI and MCP adapters."""

from __future__ import annotations


class ProjectMindError(Exception):
    """Base class for expected ProjectMind failures."""

    code = "projectmind_error"


class ConfigurationError(ProjectMindError):
    """Raised when configuration cannot be validated."""

    code = "configuration_error"


class NotFoundError(ProjectMindError):
    """Raised when a requested entity does not exist."""

    code = "not_found"


class ConflictError(ProjectMindError):
    """Raised when persisted state is stale or already consumed."""

    code = "conflict"


class SecurityError(ProjectMindError):
    """Raised when a path, patch, or command violates policy."""

    code = "security_error"


class CapabilityUnavailableError(ProjectMindError):
    """Raised when an optional local or external adapter is unavailable."""

    code = "capability_unavailable"

