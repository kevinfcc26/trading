"""XGBoost trainer — trains a 3-class classifier and saves via ModelRegistry."""
from __future__ import annotations

import logging
from datetime import datetime

from learning.domain.entities import ModelStatus, ModelVersion
from learning.infrastructure.model_registry import ModelRegistry

logger = logging.getLogger(__name__)

DEFAULT_HYPERPARAMS: dict = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "multi:softprob",
    "num_class": 3,
    "eval_metric": "mlogloss",
    "random_state": 42,
    "n_jobs": -1,
}

_METRIC_KEYS = [
    "accuracy",
    "log_loss",
    "precision_sell",
    "recall_sell",
    "f1_sell",
    "precision_hold",
    "recall_hold",
    "f1_hold",
    "precision_buy",
    "recall_buy",
    "f1_buy",
]


class XGBoostTrainer:
    """Wraps XGBClassifier with training, evaluation, and registry persistence."""

    def __init__(self, hyperparams: dict | None = None) -> None:
        self._hyperparams = {**DEFAULT_HYPERPARAMS, **(hyperparams or {})}
        self.model = None

    def train(self, X_train, y_train, X_val, y_val) -> dict:
        """Fit the XGBClassifier and return evaluation metrics.

        Returns a dict with keys matching _METRIC_KEYS (AC-3).
        Sets self.model so predict_proba is available (AC-4).
        """
        import xgboost as xgb  # type: ignore[import]
        from sklearn.metrics import accuracy_score, log_loss, precision_recall_fscore_support

        # Remove xgboost-specific keys before passing to sklearn API
        params = {k: v for k, v in self._hyperparams.items() if k != "eval_metric"}

        clf = xgb.XGBClassifier(**params)
        clf.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            early_stopping_rounds=20,
            verbose=False,
        )
        self.model = clf

        y_pred = clf.predict(X_val)
        y_proba = clf.predict_proba(X_val)

        acc = float(accuracy_score(y_val, y_pred))
        ll = float(log_loss(y_val, y_proba))

        precision, recall, f1, _ = precision_recall_fscore_support(
            y_val, y_pred, labels=[0, 1, 2], zero_division=0
        )

        metrics = {
            "accuracy": acc,
            "log_loss": ll,
            "precision_sell": float(precision[0]),
            "recall_sell": float(recall[0]),
            "f1_sell": float(f1[0]),
            "precision_hold": float(precision[1]),
            "recall_hold": float(recall[1]),
            "f1_hold": float(f1[1]),
            "precision_buy": float(precision[2]),
            "recall_buy": float(recall[2]),
            "f1_buy": float(f1[2]),
        }
        logger.info("Training complete — accuracy=%.4f log_loss=%.4f", acc, ll)
        return metrics

    def save(
        self,
        registry: ModelRegistry,
        version_str: str,
        metrics: dict,
    ) -> ModelVersion:
        """Persist model to registry.  Must call train() first.

        Order: registry.save() → registry.save_artifact() → registry.activate()
        Returns the ModelVersion record (AC-6).
        """
        if self.model is None:
            raise RuntimeError("Cannot save: model has not been trained yet.")

        version = ModelVersion(
            model_type="xgboost",
            version=version_str,
            artifact_path="",  # filled in by registry.save()
            metrics=metrics,
            status=ModelStatus.TRAINING,
        )

        registry.save(version)
        registry.save_artifact(self.model, version)
        registry.activate(version.id)

        logger.info("Model saved and activated: xgboost %s", version_str)
        return version
