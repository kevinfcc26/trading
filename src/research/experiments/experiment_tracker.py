"""Simple file-based experiment tracker for research use."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


class ExperimentTracker:
    """Track research experiments in a JSONL file.

    Usage:
        tracker = ExperimentTracker()
        exp_id = tracker.start("RSI threshold test", {"rsi_threshold": 30})
        # ... run experiment ...
        tracker.finish(exp_id, metrics={"win_rate": 0.55, "sharpe": 1.2}, notes="Promising")
    """

    def __init__(self, log_path: str | Path = "research/experiments.jsonl") -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def start(self, name: str, params: dict | None = None) -> str:
        exp_id = str(uuid4())
        record = {
            "id": exp_id,
            "name": name,
            "params": params or {},
            "started_at": datetime.utcnow().isoformat(),
            "status": "running",
            "metrics": {},
            "notes": "",
        }
        self._append(record)
        logger.info("Experiment started: %s (%s)", name, exp_id)
        return exp_id

    def finish(
        self,
        exp_id: str,
        metrics: dict | None = None,
        notes: str = "",
        status: str = "completed",
    ) -> None:
        records = self._load_all()
        for r in records:
            if r["id"] == exp_id:
                r["metrics"] = metrics or {}
                r["notes"] = notes
                r["status"] = status
                r["finished_at"] = datetime.utcnow().isoformat()
                break

        self._rewrite(records)
        logger.info("Experiment finished: %s status=%s", exp_id, status)

    def list_all(self) -> list[dict]:
        return self._load_all()

    def _append(self, record: dict) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _load_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        records = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records

    def _rewrite(self, records: list[dict]) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
