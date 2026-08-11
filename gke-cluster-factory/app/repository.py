from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


class RequestRepositoryError(RuntimeError):
    pass


class LocalRequestRepository:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def list_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.base_dir.glob("*/*.yaml")):
            try:
                record = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if isinstance(record, dict):
                record.setdefault("_path", str(path.relative_to(self.base_dir.parent)))
                records.append(record)
        return records

    def get_record(self, name: str) -> dict[str, Any] | None:
        for record in self.list_records():
            if record.get("metadata", {}).get("name") == name:
                return record
        return None

    def get_record_path(self, name: str) -> Path | None:
        for path in sorted(self.base_dir.glob("*/*.yaml")):
            try:
                record = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if isinstance(record, dict) and record.get("metadata", {}).get("name") == name:
                return path
        return None

    def write_record(self, environment: str, name: str, yaml_text: str) -> Path:
        directory = self.base_dir / environment
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{name}.yaml"
        if destination.exists():
            raise RequestRepositoryError(f"A request named {name} already exists")

        fd, temporary = tempfile.mkstemp(prefix=f".{name}-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(yaml_text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return destination
