"""
Security and execution boundary exceptions for the Autonomous Agent Workbench.
"""

from typing import Optional


class SecurityException(Exception):
    """Base class for all workbench security boundary violations."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PathTraversalError(SecurityException):
    """Raised when an operation attempts to resolve a path outside the permitted workspace."""
    pass


class PolicyViolationError(SecurityException):
    """Raised when an operation is blocked by the active execution policy."""
    pass


class ExecutionTimeoutError(SecurityException):
    """Raised when a subprocess execution exceeds its configured timeout deadline."""
    pass


class ExecutionError(SecurityException):
    """Raised when a subprocess fails execution or violates execution boundaries."""
    pass
