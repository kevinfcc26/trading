"""Domain exceptions used across all bounded contexts."""
from __future__ import annotations


class DomainException(Exception):
    """Base for all domain-level exceptions."""


class RiskViolation(DomainException):
    """Raised by the RiskPipeline when a trade violates a risk rule.

    The message must describe which rule was violated and why.
    """


class KillSwitchActive(DomainException):
    """Raised when the KillSwitch is engaged and no new trades may be opened."""


class InsufficientDataError(DomainException):
    """Raised when there is not enough market data to generate a signal."""


class BrokerConnectionError(DomainException):
    """Raised when the broker connection fails or is unavailable."""


class ModelNotFoundError(DomainException):
    """Raised when a required ML model artifact is missing."""
