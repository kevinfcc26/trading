"""Learning domain entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4


class KnowledgeType(str, Enum):
    PRINCIPLE = "PRINCIPLE"       # high-level trading principle
    RULE = "RULE"                 # specific actionable rule
    RISK_CONCEPT = "RISK_CONCEPT" # risk management concept
    INDICATOR = "INDICATOR"       # indicator description / usage
    PATTERN = "PATTERN"           # market pattern


@dataclass
class KnowledgeItem:
    """A unit of trading knowledge extracted from a document."""
    knowledge_type: KnowledgeType
    title: str
    content: str
    source_document: str = ""
    source_section: str = ""
    confidence: float = 1.0      # Claude's confidence in extraction quality
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: UUID = field(default_factory=uuid4)


@dataclass
class TradingPrinciple:
    """High-level trading principle with actionable implications."""
    title: str
    description: str
    actionable_rules: list[str] = field(default_factory=list)
    source: str = ""
    id: UUID = field(default_factory=uuid4)


class ModelStatus(str, Enum):
    TRAINING = "TRAINING"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


@dataclass
class ModelVersion:
    """Versioned ML model artifact."""
    model_type: str          # "xgboost" | "pytorch_rl"
    version: str             # e.g. "v1.2.0"
    artifact_path: str       # path to .joblib or .pt file
    metrics: dict = field(default_factory=dict)
    status: ModelStatus = ModelStatus.TRAINING
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: UUID = field(default_factory=uuid4)


@dataclass
class Experiment:
    """Record of a training experiment."""
    name: str
    model_type: str
    hyperparams: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    notes: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
