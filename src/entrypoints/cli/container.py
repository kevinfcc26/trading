"""Composition root — wires all bounded contexts.

build_container() is called once at startup and returns a fully-wired Container.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.settings import Settings
from events.bus.in_memory_bus import InMemoryEventBus
from execution.infrastructure.mt5.adapter import MT5Adapter
from execution.infrastructure.mt5.connection import MT5ConnectionManager
from execution.infrastructure.paper.adapter import PaperBrokerAdapter
from infrastructure.persistence.session import get_session_factory
from learning.infrastructure.concept_extractor import ConceptExtractor
from learning.infrastructure.document_loader import DocumentLoader
from learning.infrastructure.knowledge_store import FileKnowledgeStore
from learning.infrastructure.model_registry import ModelRegistry
from learning.infrastructure.semantic_parser import SemanticParser
from risk.domain.entities import RiskPolicy
from risk.domain.services.kill_switch import KillSwitch
from risk.domain.services.pipeline import RiskPipeline
from strategy.domain.services import SignalAggregator
from strategy.infrastructure.claude_strategy import ClaudeStrategy
from strategy.infrastructure.ml_strategy import MLStrategy
from strategy.infrastructure.ta_strategy import TAStrategy


@dataclass
class Container:
    # Event bus
    event_bus: InMemoryEventBus

    # Broker (MT5 or Paper)
    broker: MT5Adapter | PaperBrokerAdapter

    # Strategy components
    ta_strategy: TAStrategy
    ml_strategy: MLStrategy | None
    claude_strategy: ClaudeStrategy
    aggregator: SignalAggregator

    # Risk components
    kill_switch: KillSwitch
    risk_pipeline: RiskPipeline
    risk_policy: RiskPolicy

    # Learning components
    document_loader: DocumentLoader
    semantic_parser: SemanticParser
    concept_extractor: ConceptExtractor
    knowledge_store: FileKnowledgeStore
    model_registry: ModelRegistry

    # DB session factory
    session_factory: object


def build_container(
    settings: Settings,
    model_path: str | Path = "models/model.joblib",
    dry_run: bool = True,
) -> Container:
    api_key = settings.anthropic_api_key.get_secret_value()

    # Event bus
    bus = InMemoryEventBus()

    # Broker
    if dry_run:
        broker = PaperBrokerAdapter(initial_balance=10_000.0)
    else:
        conn = MT5ConnectionManager(
            login=settings.mt5_login,
            password=settings.mt5_password.get_secret_value(),
            server=settings.mt5_server,
        )
        broker = MT5Adapter(conn)

    # Strategies
    ta = TAStrategy()

    ml: MLStrategy | None = None
    try:
        ml = MLStrategy(model_path=model_path)
    except Exception:
        pass  # Model not trained yet — ML signal falls back to TA

    claude = ClaudeStrategy(api_key=api_key)

    aggregator = SignalAggregator(
        weight_ta=settings.weight_ta,
        weight_ml=settings.weight_ml,
        weight_claude=settings.weight_claude,
        min_threshold=settings.min_signal_threshold,
        claude_veto_threshold=settings.claude_veto_threshold,
    )

    # Risk
    policy = RiskPolicy(
        risk_per_trade=settings.risk_per_trade,
        max_open_positions=settings.max_open_positions,
    )
    ks = KillSwitch()
    pipeline = RiskPipeline(ks, policy)

    # Learning
    loader = DocumentLoader()
    parser = SemanticParser(api_key=api_key)
    extractor = ConceptExtractor(api_key=api_key)
    kb = FileKnowledgeStore()
    registry = ModelRegistry()

    # DB
    session_factory = get_session_factory()

    return Container(
        event_bus=bus,
        broker=broker,
        ta_strategy=ta,
        ml_strategy=ml,
        claude_strategy=claude,
        aggregator=aggregator,
        kill_switch=ks,
        risk_pipeline=pipeline,
        risk_policy=policy,
        document_loader=loader,
        semantic_parser=parser,
        concept_extractor=extractor,
        knowledge_store=kb,
        model_registry=registry,
        session_factory=session_factory,
    )
