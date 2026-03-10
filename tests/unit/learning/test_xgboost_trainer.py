"""Tests for XGBoostTrainer — AC-3, AC-4, AC-6. XGBClassifier is mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import numpy as np
import pytest

from learning.domain.entities import ModelStatus, ModelVersion
from learning.infrastructure.xgboost_trainer import XGBoostTrainer, _METRIC_KEYS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _dummy_arrays(n_train: int = 80, n_val: int = 20, n_features: int = 7):
    rng = np.random.default_rng(0)
    X_tr = rng.random((n_train, n_features))
    y_tr = rng.integers(0, 3, n_train)
    X_v = rng.random((n_val, n_features))
    y_v = rng.integers(0, 3, n_val)
    return X_tr, y_tr, X_v, y_v


def _make_mock_clf(n_val: int = 20):
    """Return a mock XGBClassifier that produces plausible predictions."""
    rng = np.random.default_rng(1)
    y_pred = rng.integers(0, 3, n_val)
    proba = rng.dirichlet([1, 1, 1], n_val)

    mock_clf = MagicMock()
    mock_clf.predict.return_value = y_pred
    mock_clf.predict_proba.return_value = proba
    return mock_clf


def _make_registry_mock(version_id=None):
    registry = MagicMock()
    mv = ModelVersion(
        model_type="xgboost",
        version="v_test",
        artifact_path="/tmp/xgboost_v_test.joblib",
        status=ModelStatus.ACTIVE,
        id=version_id or uuid4(),
    )
    registry.get_active.return_value = mv
    return registry, mv


# ---------------------------------------------------------------------------
# AC-3 / AC-4: train()
# ---------------------------------------------------------------------------

class TestXGBoostTrainerTrain:
    def _train_with_mock(self):
        X_tr, y_tr, X_v, y_v = _dummy_arrays()
        mock_clf = _make_mock_clf(len(y_v))

        with patch("xgboost.XGBClassifier", return_value=mock_clf):
            trainer = XGBoostTrainer()
            metrics = trainer.train(X_tr, y_tr, X_v, y_v)

        return trainer, metrics, y_v

    def test_train_returns_all_metric_keys(self):
        """AC-3: train() returns dict with all expected metric keys."""
        _, metrics, _ = self._train_with_mock()
        for key in _METRIC_KEYS:
            assert key in metrics, f"Missing metric key: {key}"

    def test_train_sets_self_model(self):
        """AC-4: after train(), self.model is set (not None)."""
        trainer, _, _ = self._train_with_mock()
        assert trainer.model is not None

    def test_train_metrics_are_floats(self):
        """AC-3: all metric values are Python floats."""
        _, metrics, _ = self._train_with_mock()
        for key, val in metrics.items():
            assert isinstance(val, float), f"{key} is not float: {type(val)}"


# ---------------------------------------------------------------------------
# AC-6: save()
# ---------------------------------------------------------------------------

class TestXGBoostTrainerSave:
    def _trained_trainer(self):
        X_tr, y_tr, X_v, y_v = _dummy_arrays()
        mock_clf = _make_mock_clf(len(y_v))
        with patch("xgboost.XGBClassifier", return_value=mock_clf):
            trainer = XGBoostTrainer()
            metrics = trainer.train(X_tr, y_tr, X_v, y_v)
        return trainer, metrics

    def test_save_calls_registry_save(self):
        """AC-6: save() calls registry.save() once."""
        trainer, metrics = self._trained_trainer()
        registry, _ = _make_registry_mock()
        trainer.save(registry, "v1.0.0", metrics)
        registry.save.assert_called_once()

    def test_save_calls_registry_save_artifact(self):
        """AC-6: save() calls registry.save_artifact() once."""
        trainer, metrics = self._trained_trainer()
        registry, _ = _make_registry_mock()
        trainer.save(registry, "v1.0.0", metrics)
        registry.save_artifact.assert_called_once()

    def test_save_calls_registry_activate(self):
        """AC-6: save() calls registry.activate() once."""
        trainer, metrics = self._trained_trainer()
        registry, _ = _make_registry_mock()
        trainer.save(registry, "v1.0.0", metrics)
        registry.activate.assert_called_once()

    def test_save_raises_if_model_not_trained(self):
        """AC-4: save() before train() raises RuntimeError."""
        trainer = XGBoostTrainer()
        registry, _ = _make_registry_mock()
        with pytest.raises(RuntimeError, match="not been trained"):
            trainer.save(registry, "v1.0.0", {})

    def test_save_returns_model_version(self):
        """AC-6: save() returns a ModelVersion instance."""
        trainer, metrics = self._trained_trainer()
        registry, _ = _make_registry_mock()
        result = trainer.save(registry, "v1.0.0", metrics)
        assert isinstance(result, ModelVersion)
