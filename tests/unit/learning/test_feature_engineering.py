"""Tests for FeatureEngineer — AC-1, AC-2, AC-7."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from learning.infrastructure.feature_engineering import FEATURE_NAMES, FeatureEngineer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 200, drift: float = 0.0) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with `n` rows."""
    rng = np.random.default_rng(42)
    close = 1.1000 + drift * np.arange(n) + rng.normal(0, 0.001, n).cumsum()
    df = pd.DataFrame(
        {
            "open": close - 0.0002,
            "high": close + 0.0010,
            "low": close - 0.0010,
            "close": close,
            "volume": rng.integers(100, 1000, n).astype(float),
        }
    )
    return df


def _write_csv(df: pd.DataFrame) -> str:
    """Write df to a temp CSV and return the path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# AC-1: build_feature_matrix
# ---------------------------------------------------------------------------

class TestBuildFeatureMatrix:
    def setup_method(self):
        self.fe = FeatureEngineer()
        self.df = _make_ohlcv(200)
        self.features = self.fe.build_feature_matrix(self.df)

    def test_build_columns_exact_order(self):
        """AC-1: columns are exactly FEATURE_NAMES in that order."""
        assert list(self.features.columns) == FEATURE_NAMES

    def test_build_no_nan_rows(self):
        """AC-1: no NaN values survive after warmup drop."""
        assert not self.features.isnull().any().any()

    def test_build_column_count_matches_feature_names(self):
        """AC-1: column count matches FEATURE_NAMES (currently 17)."""
        assert len(self.features.columns) == len(FEATURE_NAMES)

    def test_build_drops_warmup_rows(self):
        """AC-1: warmup rows with NaN indicators are removed; row count < input."""
        assert len(self.features) < len(self.df)


# ---------------------------------------------------------------------------
# AC-2: generate_labels
# ---------------------------------------------------------------------------

class TestGenerateLabels:
    def setup_method(self):
        self.fe = FeatureEngineer()
        self.df = _make_ohlcv(200)

    def test_labels_valid_values_only(self):
        """AC-2: all labels are in {0, 1, 2}."""
        labels = self.fe.generate_labels(self.df)
        assert set(labels.unique()).issubset({0, 1, 2})

    def test_labels_no_future_look_last_horizon(self):
        """AC-2: last `horizon` rows of the original df are excluded."""
        horizon = 5
        labels = self.fe.generate_labels(self.df, horizon=horizon)
        # The label series should not contain the last `horizon` rows' indices
        last_indices = self.df.index[-horizon:]
        assert not any(idx in labels.index for idx in last_indices)

    def test_labels_index_subset_of_features(self):
        """AC-2: labels and features share a non-empty common index after inner-join.

        Uses 500 rows so EMA200 warmup (199 bars) still leaves overlap with labels.
        """
        df = _make_ohlcv(500)
        features = self.fe.build_feature_matrix(df)
        labels = self.fe.generate_labels(df)
        common_idx = features.index.intersection(labels.index)
        assert len(common_idx) > 0, "No common indices between features and labels"
        assert set(labels.loc[common_idx].unique()).issubset({0, 1, 2})

    def test_labels_all_hold_with_huge_threshold(self):
        """AC-2: with threshold=1.0 (100%), every label is 1 (HOLD)."""
        labels = self.fe.generate_labels(self.df, threshold=1.0)
        assert (labels == 1).all()

    def test_labels_buy_dominant_with_rising_price(self):
        """AC-2: strongly rising prices produce mostly BUY (2) labels."""
        rising_df = _make_ohlcv(300, drift=0.01)  # large positive drift
        labels = self.fe.generate_labels(rising_df, horizon=5, threshold=0.0002)
        buy_ratio = (labels == 2).mean()
        assert buy_ratio > 0.5, f"Expected >50% BUY labels, got {buy_ratio:.2%}"


# ---------------------------------------------------------------------------
# AC-7 / AC-1: load_csv
# ---------------------------------------------------------------------------

class TestLoadCsv:
    def setup_method(self):
        self.fe = FeatureEngineer()

    def test_load_csv_raises_file_not_found(self):
        """AC-7: non-existent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            self.fe.load_csv("/nonexistent/path/data.csv")

    def test_load_csv_raises_value_error_missing_columns(self):
        """AC-1: CSV missing required OHLCV columns raises ValueError."""
        bad_df = pd.DataFrame({"price": [1.0, 2.0, 3.0]})
        path = _write_csv(bad_df)
        try:
            with pytest.raises(ValueError, match="missing required columns"):
                self.fe.load_csv(path)
        finally:
            os.unlink(path)
