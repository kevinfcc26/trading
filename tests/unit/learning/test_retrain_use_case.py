"""Tests for RetrainModelUseCase — AC-5, AC-6, AC-7, AC-8. All deps mocked."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from learning.domain.entities import Experiment, ModelStatus, ModelVersion
from learning.infrastructure.xgboost_trainer import _METRIC_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_METRICS = {k: 0.5 for k in _METRIC_KEYS}


def _make_csv() -> str:
    """Write a minimal valid OHLCV CSV, return path."""
    rng = np.random.default_rng(7)
    n = 200
    close = 1.1 + rng.normal(0, 0.001, n).cumsum()
    df = pd.DataFrame({
        "open": close - 0.0002,
        "high": close + 0.001,
        "low": close - 0.001,
        "close": close,
        "volume": rng.integers(100, 1000, n).astype(float),
    })
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return tmp.name


def _build_use_case(csv_path: str | None = None):
    """Return (use_case, mock_registry, mock_trainer, mock_fe, csv_path)."""
    from learning.application.use_cases import RetrainModelUseCase

    registry = MagicMock()
    trainer = MagicMock()
    fe = MagicMock()

    # trainer.train returns dummy metrics
    trainer.train.return_value = _DUMMY_METRICS.copy()

    # trainer.save returns a ModelVersion
    mv = ModelVersion(
        model_type="xgboost",
        version="v20240101_000000",
        artifact_path="/tmp/model.joblib",
        status=ModelStatus.ACTIVE,
        metrics=_DUMMY_METRICS,
        id=uuid4(),
    )
    trainer.save.return_value = mv

    # Feature engineer returns DataFrames that work together
    n = 200
    rng = np.random.default_rng(8)
    close = 1.1 + rng.normal(0, 0.001, n).cumsum()
    raw_df = pd.DataFrame({
        "open": close - 0.0002,
        "high": close + 0.001,
        "low": close - 0.001,
        "close": close,
        "volume": rng.integers(100, 1000, n).astype(float),
    })

    from learning.infrastructure.feature_engineering import FEATURE_NAMES
    feat_data = {col: rng.random(n) for col in FEATURE_NAMES}
    features_df = pd.DataFrame(feat_data, index=range(n))
    labels_series = pd.Series(rng.integers(0, 3, n - 5), index=range(n - 5))

    fe.load_csv.return_value = raw_df
    fe.build_feature_matrix.return_value = features_df
    fe.generate_labels.return_value = labels_series

    path = csv_path or _make_csv()
    uc = RetrainModelUseCase(registry=registry, trainer=trainer, feature_engineer=fe)
    return uc, registry, trainer, fe, path


# ---------------------------------------------------------------------------
# AC-5: execute() returns completed Experiment
# ---------------------------------------------------------------------------

class TestRetrainUseCaseExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_experiment_with_finished_at(self):
        """AC-5: execute() returns an Experiment with finished_at set."""
        uc, _, _, _, path = _build_use_case()
        try:
            result = await uc.execute(training_data_path=path)
            assert isinstance(result, Experiment)
            assert result.finished_at is not None
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_execute_metrics_present(self):
        """AC-5: experiment.metrics contains all AC-3 keys."""
        uc, _, _, _, path = _build_use_case()
        try:
            result = await uc.execute(training_data_path=path)
            for key in _METRIC_KEYS:
                assert key in result.metrics, f"Missing metric: {key}"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_execute_activates_model(self):
        """AC-6: execute() calls trainer.save() to trigger activation."""
        uc, registry, trainer, _, path = _build_use_case()
        try:
            await uc.execute(training_data_path=path)
            trainer.save.assert_called_once()
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_execute_default_model_type_xgboost(self):
        """AC-5: default model_type is 'xgboost'."""
        uc, _, trainer, _, path = _build_use_case()
        try:
            result = await uc.execute(training_data_path=path)
            assert result.model_type == "xgboost"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_execute_records_hyperparams(self):
        """AC-5: hyperparams passed in are stored in the experiment."""
        uc, _, _, _, path = _build_use_case()
        custom = {"max_depth": 4, "n_estimators": 100}
        try:
            result = await uc.execute(training_data_path=path, hyperparams=custom)
            assert result.hyperparams == custom
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# AC-7: FileNotFoundError
# ---------------------------------------------------------------------------

class TestRetrainUseCaseFileNotFound:
    @pytest.mark.asyncio
    async def test_execute_raises_file_not_found(self):
        """AC-7: non-existent path raises FileNotFoundError."""
        uc, _, _, _, _ = _build_use_case()
        with pytest.raises(FileNotFoundError):
            await uc.execute(training_data_path="/nonexistent/path/data.csv")

    @pytest.mark.asyncio
    async def test_execute_raises_file_not_found_when_none(self):
        """AC-7: None path raises FileNotFoundError."""
        uc, _, _, _, _ = _build_use_case()
        with pytest.raises(FileNotFoundError):
            await uc.execute(training_data_path=None)


# ---------------------------------------------------------------------------
# AC-8: FAILED version saved on training error
# ---------------------------------------------------------------------------

class TestRetrainUseCaseOnTrainError:
    @pytest.mark.asyncio
    async def test_execute_marks_failed_on_train_error(self):
        """AC-8: on training failure, a FAILED ModelVersion is saved."""
        from learning.application.use_cases import RetrainModelUseCase

        registry = MagicMock()
        trainer = MagicMock()
        fe = MagicMock()

        n = 200
        rng = np.random.default_rng(9)
        close = 1.1 + rng.normal(0, 0.001, n).cumsum()
        raw_df = pd.DataFrame({
            "open": close - 0.0002,
            "high": close + 0.001,
            "low": close - 0.001,
            "close": close,
            "volume": rng.integers(100, 1000, n).astype(float),
        })

        from learning.infrastructure.feature_engineering import FEATURE_NAMES
        feat_data = {col: rng.random(n) for col in FEATURE_NAMES}
        features_df = pd.DataFrame(feat_data, index=range(n))
        labels_series = pd.Series(rng.integers(0, 3, n - 5), index=range(n - 5))

        fe.load_csv.return_value = raw_df
        fe.build_feature_matrix.return_value = features_df
        fe.generate_labels.return_value = labels_series

        trainer.train.side_effect = RuntimeError("GPU out of memory")

        path = _make_csv()
        uc = RetrainModelUseCase(registry=registry, trainer=trainer, feature_engineer=fe)
        try:
            with pytest.raises(RuntimeError, match="GPU out of memory"):
                await uc.execute(training_data_path=path)

            # registry.save must have been called with a FAILED version
            registry.save.assert_called_once()
            saved_version: ModelVersion = registry.save.call_args[0][0]
            assert saved_version.status == ModelStatus.FAILED
        finally:
            os.unlink(path)
