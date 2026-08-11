#!/usr/bin/env python3
"""Validate a GKE cluster request against schema and platform policy."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

# Allow the command to run directly from any working directory.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.config import Settings  # noqa: E402
from app.models import ClusterRequestCreate  # noqa: E402
from app.service import ClusterFactoryService, RequestValidationError  # noqa: E402


def load_document(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Request file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("Request document must be a YAML mapping")
    return document


def request_payload(document: dict[str, Any]) -> dict[str, Any]:
    payload = document.get("spec", document)
    if not isinstance(payload, dict):
        raise ValueError("Request spec must be a YAML mapping")
    return payload


def validate(path: Path, repository_root: Path) -> tuple[ClusterRequestCreate, list[str]]:
    document = load_document(path)
    request = ClusterRequestCreate.model_validate(request_payload(document))
    settings = Settings(_env_file=None, root_dir=repository_root, storage_mode="local")
    service = ClusterFactoryService(settings)
    result = service.validate(request)
    return request, result.warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()

    try:
        request, warnings = validate(args.request, args.repository_root)
    except (ValueError, ValidationError, RequestValidationError) as exc:
        if isinstance(exc, RequestValidationError):
            for error in exc.errors:
                print(f"ERROR: {error}", file=sys.stderr)
            for warning in exc.warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"VALID: {request.name} ({request.environment.value}, {request.blueprint})")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
