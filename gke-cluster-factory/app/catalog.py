from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


class CatalogError(RuntimeError):
    pass


@lru_cache(maxsize=8)
def load_yaml(path_string: str, mtime_ns: int) -> dict[str, Any]:
    del mtime_ns
    path = Path(path_string)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise CatalogError(f"Configuration file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise CatalogError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogError(f"Expected a mapping in {path}")
    return data


def load_catalog(path: Path) -> dict[str, Any]:
    return load_yaml(str(path), path.stat().st_mtime_ns)


def get_profile(catalog: dict[str, Any], profile_name: str) -> dict[str, Any]:
    profiles = catalog.get("profiles", {})
    profile = profiles.get(profile_name)
    if not profile:
        raise CatalogError(f"Unknown blueprint: {profile_name}")
    return profile
