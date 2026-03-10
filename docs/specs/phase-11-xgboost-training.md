# Phase 11 — XGBoost Model Training

**Status:** DONE

---

## 1. Goal

Implement `RetrainModelUseCase.execute()` so that a CSV of OHLCV candles produces a
trained, versioned, and activated XGBoost model that `MLStrategy` can load immediately
without manual file copying. The `NotImplementedError` placeholder is replaced with a
complete feature-engineering → training → registry pipeline.

---

## 2. Scope

**In scope:**
- Feature engineering from OHLCV CSV (RSI, EMA diff, MACD, BB width, close, volume)
- 3-class label generation (0=SELL, 1=HOLD, 2=BUY) based on forward return
- Time-ordered 80/20 train/val split (no shuffle)
- `XGBClassifier` training with early stopping
- Evaluation metrics: accuracy, log_loss, per-class precision/recall/f1
- `ModelRegistry` integration: save metadata → save artifact → activate
- Unit tests for all three new classes (26 tests total)

**Out of scope:**
- Walk-forward cross-validation
- Hyperparameter tuning (Optuna/grid search)
- RL agent training (Phase 12)
- New CLI `retrain` command (future)
- Live/streaming feature computation (handled by `MLStrategy._extract_features`)

---

## 3. Domain Concepts

| Concept | Definition |
|---------|-----------|
| `FeatureEngineer` | Transforms raw OHLCV DataFrame into model-ready feature matrix and labels |
| `FEATURE_NAMES` | Canonical ordered list of 7 feature column names — single source of truth |
| `XGBoostTrainer` | Wraps XGBClassifier; produces metrics and persists via ModelRegistry |
| `Experiment` | Domain entity recording hyperparams, metrics, start/finish timestamps |
| `ModelVersion` | Registry record with artifact path and status (TRAINING→ACTIVE or FAILED) |
| Forward return | `(close.shift(-horizon) - close) / close` — basis for label generation |

---

## 4. Acceptance Criteria

- **AC-1** `FeatureEngineer.build_feature_matrix(df)` returns a DataFrame with exactly
  `["rsi_14","ema_diff","macd","macd_signal","bb_width","close","volume"]` columns,
  no NaN rows.
- **AC-2** `FeatureEngineer.generate_labels(df, horizon, threshold)` returns a Series
  of values in `{0,1,2}` with the last `horizon` rows excluded.
- **AC-3** `XGBoostTrainer.train(X_tr, y_tr, X_v, y_v)` returns a dict with keys:
  `accuracy`, `log_loss`, `precision_sell`, `recall_sell`, `f1_sell`,
  `precision_hold`, `recall_hold`, `f1_hold`, `precision_buy`, `recall_buy`, `f1_buy`.
- **AC-4** After `train()`, `self.model` is not None and has a `predict_proba` attribute.
- **AC-5** `RetrainModelUseCase.execute()` returns an `Experiment` with `finished_at`
  set (not None) and a `metrics` dict containing the AC-3 keys.
- **AC-6** After a successful `execute()`, `ModelRegistry.get_active("xgboost")` returns
  a `ModelVersion` with `status == ModelStatus.ACTIVE`.
- **AC-7** Passing a non-existent `training_data_path` raises `FileNotFoundError`.
- **AC-8** If training raises an exception, a `ModelVersion` with `ModelStatus.FAILED`
  is saved before re-raising.

---

## 5. Files to Create or Modify

| # | File | Action | Notes |
|---|------|--------|-------|
| 1 | `docs/specs/TEMPLATE.md` | CREATE | SDD canonical template |
| 2 | `docs/specs/phase-11-xgboost-training.md` | CREATE | This file |
| 3 | `tests/unit/learning/__init__.py` | CREATE | Empty pytest package |
| 4 | `src/learning/infrastructure/feature_engineering.py` | CREATE | FEATURE_NAMES, FeatureEngineer |
| 5 | `src/learning/infrastructure/xgboost_trainer.py` | CREATE | XGBoostTrainer, DEFAULT_HYPERPARAMS |
| 6 | `src/learning/application/use_cases.py` | MODIFY | Implement RetrainModelUseCase |
| 7 | `src/strategy/infrastructure/ml_strategy.py` | MODIFY | Import FEATURE_NAMES from feature_engineering |
| 8 | `tests/unit/learning/test_feature_engineering.py` | CREATE | 11 tests |
| 9 | `tests/unit/learning/test_xgboost_trainer.py` | CREATE | 8 tests |
| 10 | `tests/unit/learning/test_retrain_use_case.py` | CREATE | 7 tests |
| 11 | `docs/ai_context.md` | MODIFY | Phase 11 → ✅ Done |
| 12 | `docs/specs/phase-11-xgboost-training.md` | MODIFY | Status → DONE |

---

## 6. API / Signatures

### `src/learning/infrastructure/feature_engineering.py`

```python
FEATURE_NAMES: list[str] = [
    "rsi_14", "ema_diff", "macd", "macd_signal", "bb_width", "close", "volume"
]

class FeatureEngineer:
    def build_feature_matrix(self, df: pd.DataFrame) -> pd.DataFrame: ...
    def generate_labels(
        self, df: pd.DataFrame, horizon: int = 5, threshold: float = 0.0002
    ) -> pd.Series: ...
    def load_csv(self, path: str | Path) -> pd.DataFrame: ...
```

**Rules:**
- Uses `pandas_ta`: `rsi(14)`, `macd()`, `ema(20)`, `ema(50)`, `bbands(20)`
- `ema_diff = EMA_20 - EMA_50`
- `bb_width = BBU_20_2.0 - BBL_20_2.0`
- Drops NaN warmup rows before returning
- Labels: forward_return > +threshold → 2 (BUY); < -threshold → 0 (SELL); else 1 (HOLD)
- Last `horizon` rows excluded from labels (no future leakage)

### `src/learning/infrastructure/xgboost_trainer.py`

```python
DEFAULT_HYPERPARAMS = {
    "n_estimators": 300, "max_depth": 6, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "objective": "multi:softprob", "num_class": 3,
    "eval_metric": "mlogloss", "random_state": 42, "n_jobs": -1,
}

class XGBoostTrainer:
    def __init__(self, hyperparams: dict | None = None) -> None: ...
    def train(self, X_train, y_train, X_val, y_val) -> dict: ...
    def save(
        self, registry: ModelRegistry, version_str: str, metrics: dict
    ) -> ModelVersion: ...
```

**Rules:**
- `train()`: lazy `import xgboost`; fit with `early_stopping_rounds=20`; compute
  accuracy, log_loss, per-class precision/recall/f1 via `sklearn.metrics`
- `save()`: raises `RuntimeError` if called before `train()`; calls
  `registry.save()` → `registry.save_artifact()` → `registry.activate()` in that order

### `src/learning/application/use_cases.py` — `RetrainModelUseCase`

```python
class RetrainModelUseCase:
    def __init__(
        self,
        registry: ModelRegistry,
        trainer: XGBoostTrainer | None = None,
        feature_engineer: FeatureEngineer | None = None,
    ) -> None: ...

    async def execute(
        self,
        model_type: str = "xgboost",
        training_data_path: str | None = None,
        hyperparams: dict | None = None,
        horizon: int = 5,
        label_threshold: float = 0.0002,
        val_split: float = 0.2,
        version: str | None = None,
    ) -> Experiment: ...
```

**Execute flow:**
1. Raise `FileNotFoundError` if `training_data_path` is None or file does not exist
2. `fe.load_csv()` → raw df
3. `fe.build_feature_matrix()` + `fe.generate_labels()`, inner-join on index
4. Time-ordered 80/20 split (no shuffle)
5. `trainer.train()` → metrics; on exception, save `ModelStatus.FAILED` version, re-raise
6. `trainer.save(registry, version_str, metrics)`
7. Return `Experiment` with `finished_at` set

---

## 7. Test Plan

### `test_feature_engineering.py` (11 tests)

| Test | AC |
|------|----|
| `test_build_columns_exact_order` | AC-1 |
| `test_build_no_nan_rows` | AC-1 |
| `test_build_column_count_is_7` | AC-1 |
| `test_build_drops_warmup_rows` | AC-1 |
| `test_labels_valid_values_only` | AC-2 |
| `test_labels_no_future_look_last_horizon` | AC-2 |
| `test_labels_index_subset_of_features` | AC-2 |
| `test_labels_all_hold_with_huge_threshold` | AC-2 |
| `test_labels_buy_dominant_with_rising_price` | AC-2 |
| `test_load_csv_raises_file_not_found` | AC-7 |
| `test_load_csv_raises_value_error_missing_columns` | AC-1 |

### `test_xgboost_trainer.py` (8 tests, XGBClassifier mocked)

| Test | AC |
|------|----|
| `test_train_returns_all_metric_keys` | AC-3 |
| `test_train_sets_self_model` | AC-4 |
| `test_train_metrics_are_floats` | AC-3 |
| `test_save_calls_registry_save` | AC-6 |
| `test_save_calls_registry_save_artifact` | AC-6 |
| `test_save_calls_registry_activate` | AC-6 |
| `test_save_raises_if_model_not_trained` | AC-4 |
| `test_save_returns_model_version` | AC-6 |

### `test_retrain_use_case.py` (7 tests, all deps mocked)

| Test | AC |
|------|----|
| `test_execute_returns_experiment_with_finished_at` | AC-5 |
| `test_execute_metrics_present` | AC-5 |
| `test_execute_activates_model` | AC-6 |
| `test_execute_raises_file_not_found` | AC-7 |
| `test_execute_marks_failed_on_train_error` | AC-8 |
| `test_execute_default_model_type_xgboost` | AC-5 |
| `test_execute_records_hyperparams` | AC-5 |

---

## 8. Dependencies and Risks

| Item | Type | Mitigation |
|------|------|-----------|
| `xgboost` package | Dependency | Already in pyproject.toml; lazy import in `train()` |
| `pandas_ta` package | Dependency | Already installed; lazy import in `build_feature_matrix()` |
| FEATURE_NAMES mismatch between training & inference | Risk | Import from single source (`feature_engineering.py`) |
| XGBoost `early_stopping_rounds` requires eval_set | Risk | Always pass `eval_set=[(X_val, y_val)]` |
| CSV missing required OHLCV columns | Risk | `load_csv()` raises `ValueError` with clear message |

---

## 9. Implementation Notes

- Feature column renaming: `pandas_ta` outputs e.g. `RSI_14`, `MACD_12_26_9`,
  `MACDs_12_26_9`, `EMA_20`, `EMA_50`, `BBU_20_2.0`, `BBL_20_2.0` — rename to
  `FEATURE_NAMES` canonical names inside `build_feature_matrix()`.
- Label generation: compute forward return first, then apply threshold, then drop last
  `horizon` rows to avoid NaN contamination.
- `val_split` in `execute()`: `split_idx = int(len(df) * (1 - val_split))`.
- `ModelVersion` starts with `status=ModelStatus.TRAINING`; `activate()` changes it
  to `ACTIVE` in the registry metadata (the in-memory object stays TRAINING).
- On training failure: create a `ModelVersion` with `status=ModelStatus.FAILED`,
  call `registry.save()` (metadata only, no artifact), then re-raise the exception.
- Version string: use `f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"` if not passed.

---

## 10. Done Checklist

- [x] `docs/specs/TEMPLATE.md` created
- [x] `docs/specs/phase-11-xgboost-training.md` created
- [x] All 26 new unit tests pass
- [x] `poetry run pytest tests/unit/` fully green (27 + 26 = 53 tests)
- [x] `FEATURE_NAMES` imported by `ml_strategy.py` from `feature_engineering.py`
- [x] `docs/ai_context.md` Phase 11 → ✅ Done
- [x] This spec status → DONE
