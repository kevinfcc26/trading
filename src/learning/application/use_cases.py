"""Learning application use cases."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from learning.domain.entities import Experiment, KnowledgeItem, KnowledgeType, ModelStatus, ModelVersion
from learning.domain.ports import KnowledgeBasePort
from learning.infrastructure.concept_extractor import ConceptExtractor
from learning.infrastructure.document_loader import DocumentLoader
from learning.infrastructure.feature_engineering import FeatureEngineer
from learning.infrastructure.model_registry import ModelRegistry
from learning.infrastructure.semantic_parser import SemanticParser
from learning.infrastructure.xgboost_trainer import XGBoostTrainer

logger = logging.getLogger(__name__)


class IngestDocumentUseCase:
    """Full knowledge ingestion pipeline:
    File → DocumentLoader → raw_text
    raw_text → SemanticParser → sections
    sections → ConceptExtractor → KnowledgeItems
    KnowledgeItems → KnowledgeBasePort (persisted)
    """

    def __init__(
        self,
        loader: DocumentLoader,
        parser: SemanticParser,
        extractor: ConceptExtractor,
        knowledge_base: KnowledgeBasePort,
    ) -> None:
        self._loader = loader
        self._parser = parser
        self._extractor = extractor
        self._kb = knowledge_base

    async def execute(self, file_path: str | Path) -> list[KnowledgeItem]:
        path = Path(file_path)
        logger.info("Starting ingestion: %s", path.name)

        # Load
        raw_text = self._loader.load(path)
        logger.info("Loaded %d chars", len(raw_text))

        # Parse into sections
        sections = self._parser.parse(raw_text, document_name=path.name)
        logger.info("Parsed %d sections", len(sections))

        # Extract knowledge items
        items = self._extractor.extract_all(sections, source_document=path.name)
        logger.info("Extracted %d knowledge items", len(items))

        # Persist
        saved = []
        for item in items:
            saved_item = await self._kb.save(item)
            saved.append(saved_item)

        logger.info("Ingestion complete: %d items saved from %s", len(saved), path.name)
        return saved


class QueryKnowledgeUseCase:
    """Retrieve knowledge items by type."""

    def __init__(self, knowledge_base: KnowledgeBasePort) -> None:
        self._kb = knowledge_base

    async def execute(self, knowledge_type: str | None = None) -> list[KnowledgeItem]:
        return await self._kb.get_all(knowledge_type)


class RetrainModelUseCase:
    """Train an XGBoost classifier from a CSV of OHLCV candles and activate it."""

    def __init__(
        self,
        registry: ModelRegistry,
        trainer: XGBoostTrainer | None = None,
        feature_engineer: FeatureEngineer | None = None,
    ) -> None:
        self._registry = registry
        self._trainer = trainer or XGBoostTrainer()
        self._fe = feature_engineer or FeatureEngineer()

    async def execute(
        self,
        model_type: str = "xgboost",
        training_data_path: str | None = None,
        hyperparams: dict | None = None,
        horizon: int = 5,
        label_threshold: float = 0.0002,
        val_split: float = 0.2,
        version: str | None = None,
    ) -> Experiment:
        """Run the full training pipeline and return a completed Experiment.

        Raises FileNotFoundError if training_data_path is None or missing.
        On training failure, saves a FAILED ModelVersion before re-raising.
        """
        # AC-7: path validation
        if training_data_path is None:
            raise FileNotFoundError("training_data_path must be provided")
        path = Path(training_data_path)
        if not path.exists():
            raise FileNotFoundError(f"Training data not found: {path}")

        version_str = version or f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        experiment = Experiment(
            name=f"{model_type}_{version_str}",
            model_type=model_type,
            hyperparams=hyperparams or {},
        )

        logger.info("RetrainModelUseCase: loading %s", path)

        # Feature engineering
        raw_df = self._fe.load_csv(path)
        features = self._fe.build_feature_matrix(raw_df)
        labels = self._fe.generate_labels(raw_df, horizon=horizon, threshold=label_threshold)

        # Inner-join on index to align features and labels
        aligned = features.join(labels.rename("label"), how="inner")
        X = aligned.drop(columns=["label"])
        y = aligned["label"]

        # Time-ordered split (no shuffle)
        split_idx = int(len(X) * (1 - val_split))
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        # Training — save FAILED version on error (AC-8)
        try:
            metrics = self._trainer.train(X_train, y_train, X_val, y_val)
        except Exception:
            failed_version = ModelVersion(
                model_type=model_type,
                version=version_str,
                artifact_path="",
                metrics={},
                status=ModelStatus.FAILED,
            )
            self._registry.save(failed_version)
            logger.error("Training failed — FAILED version saved for %s %s", model_type, version_str)
            raise

        # Persist and activate (AC-6)
        self._trainer.save(self._registry, version_str, metrics)

        experiment.metrics = metrics
        experiment.finished_at = datetime.utcnow()
        logger.info("Experiment complete: %s accuracy=%.4f", experiment.name, metrics.get("accuracy", 0))
        return experiment


class RunRLEpisodeUseCase:
    """Run one episode of the RL environment for training or evaluation."""

    async def execute(
        self,
        candles_df,
        policy_fn=None,
        render: bool = False,
    ) -> dict:
        from learning.infrastructure.rl_environment import TradingEnv

        env = TradingEnv(candles_df)
        obs, info = env.reset()
        total_reward = 0.0
        steps = 0

        while True:
            if policy_fn is not None:
                action = policy_fn(obs)
            else:
                action = env.action_space.sample()  # random baseline

            obs, reward, done, truncated, info = env.step(action)
            total_reward += reward
            steps += 1

            if done or truncated:
                break

        result = {
            "total_reward": total_reward,
            "steps": steps,
            "final_balance": info.get("balance", 0),
            "total_trades": info.get("total_trades", 0),
        }
        logger.info("RL episode: reward=%.4f balance=%.2f trades=%d", total_reward, result["final_balance"], result["total_trades"])
        return result
