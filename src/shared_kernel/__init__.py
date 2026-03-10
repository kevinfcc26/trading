"""Shared Kernel — cross-cutting primitives imported by all bounded contexts."""
from .domain_event import DomainEvent
from .entity import Entity
from .exceptions import DomainException, KillSwitchActive, RiskViolation
from .value_object import ValueObject

__all__ = [
    "DomainEvent",
    "Entity",
    "ValueObject",
    "DomainException",
    "RiskViolation",
    "KillSwitchActive",
]
