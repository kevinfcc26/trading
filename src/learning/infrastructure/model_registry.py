"""ModelRegistry — versioned ML model storage using joblib + metadata JSON."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

import joblib  # type: ignore[import]

from learning.domain.entities import ModelStatus, ModelVersion

logger = logging.getLogger(__name__)


class ModelRegistry:
    """File-based model registry: artifact (.joblib/.pt) + metadata (.json)."""

    def __init__(self, registry_path: str | Path = "models/registry") -> None:
        self._root = Path(registry_path)
        self._root.mkdir(parents=True, exist_ok=True)
        self._meta_path = self._root / "versions.json"
        self._versions: list[dict] = self._load_meta()

    def _load_meta(self) -> list[dict]:
        if not self._meta_path.exists():
            return []
        with self._meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save_meta(self) -> None:
        with self._meta_path.open("w", encoding="utf-8") as f:
            json.dump(self._versions, f, indent=2, default=str)

    def save(self, version: ModelVersion) -> None:
        artifact_path = self._root / f"{version.model_type}_{version.version}.joblib"
        version.artifact_path = str(artifact_path)

        meta = {
            "id": str(version.id),
            "model_type": version.model_type,
            "version": version.version,
            "artifact_path": version.artifact_path,
            "metrics": version.metrics,
            "status": version.status.value,
            "created_at": version.created_at.isoformat(),
        }
        self._versions.append(meta)
        self._save_meta()
        logger.info("Registered model: %s %s", version.model_type, version.version)

    def save_artifact(self, model_object, version: ModelVersion) -> None:
        """Persist the actual model object to disk."""
        artifact_path = Path(version.artifact_path)
        joblib.dump(model_object, artifact_path)
        logger.info("Saved artifact: %s", artifact_path)

    def load(self, version_id: UUID) -> object:
        version = self.get_by_id(version_id)
        if version is None:
            raise FileNotFoundError(f"Model version {version_id} not found in registry")
        return joblib.load(version.artifact_path)

    def load_artifact(self, version: ModelVersion) -> object:
        return joblib.load(version.artifact_path)

    def list_versions(self, model_type: str | None = None) -> list[ModelVersion]:
        results = []
        for m in self._versions:
            if model_type and m["model_type"] != model_type:
                continue
            results.append(self._dict_to_version(m))
        return results

    def get_active(self, model_type: str) -> ModelVersion | None:
        for m in reversed(self._versions):
            if m["model_type"] == model_type and m["status"] == ModelStatus.ACTIVE.value:
                return self._dict_to_version(m)
        return None

    def get_by_id(self, version_id: UUID) -> ModelVersion | None:
        for m in self._versions:
            if m["id"] == str(version_id):
                return self._dict_to_version(m)
        return None

    def activate(self, version_id: UUID) -> None:
        """Set a version as ACTIVE and archive any previous ACTIVE of same type."""
        target = self.get_by_id(version_id)
        if target is None:
            raise ValueError(f"Version {version_id} not found")

        for m in self._versions:
            if m["model_type"] == target.model_type and m["status"] == ModelStatus.ACTIVE.value:
                m["status"] = ModelStatus.ARCHIVED.value
            if m["id"] == str(version_id):
                m["status"] = ModelStatus.ACTIVE.value

        self._save_meta()
        logger.info("Activated model: %s %s", target.model_type, target.version)

    @staticmethod
    def _dict_to_version(m: dict) -> ModelVersion:
        return ModelVersion(
            id=UUID(m["id"]),
            model_type=m["model_type"],
            version=m["version"],
            artifact_path=m["artifact_path"],
            metrics=m.get("metrics", {}),
            status=ModelStatus(m["status"]),
            created_at=datetime.fromisoformat(m["created_at"]),
        )
