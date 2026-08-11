#!/usr/bin/env python3
"""Render a validated cluster request as Terraform JSON variables."""

from __future__ import annotations

import argparse
import json
import os
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


def load(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Request must be a YAML mapping")
    return document


def render(document: dict[str, Any], root: Path) -> dict[str, Any]:
    spec = document.get("spec", document)
    if not isinstance(spec, dict):
        raise ValueError("Request spec must be a mapping")
    request = ClusterRequestCreate.model_validate(spec)
    settings = Settings(_env_file=None, root_dir=root, storage_mode="local")
    validation = ClusterFactoryService(settings).validate(request)
    normalized = validation.normalized or request.model_dump(mode="json")

    resolved = document.get("resolved", {}).get("network", {})
    required_network = {
        "node_cidr",
        "pod_cidr",
        "service_cidr",
        "control_plane_cidr",
        "subnet_name",
        "pod_range_name",
        "service_range_name",
    }
    missing = sorted(required_network - set(resolved))
    if missing:
        raise ValueError(f"Request is missing resolved network values: {', '.join(missing)}")

    catalog = yaml.safe_load((root / "config" / "profiles.yaml").read_text(encoding="utf-8"))
    profile = catalog["profiles"][request.blueprint]
    node_locations = catalog.get("node_locations", {}).get(request.region, [])

    return {
        "cluster_name": request.name,
        "project_id": request.project_id,
        "region": request.region,
        "node_locations": node_locations,
        "environment": request.environment.value,
        "blueprint": request.blueprint,
        "owner_group": str(request.owner.google_group),
        "gke_security_group": os.environ.get(
            "GKE_SECURITY_GROUP", catalog.get("gke_security_group", "gke-security-groups@example.com")
        ),
        "platform_admin_group": os.environ.get(
            "PLATFORM_ADMIN_GROUP", catalog.get("platform_admin_group", "gke-platform-admins@example.com")
        ),
        "technical_contact": str(request.owner.technical_contact or request.owner.google_group),
        "labels": normalized.get("labels", {}),
        "system_machine_type": profile["system_machine_type"],
        "general_machine_type": profile["general_machine_type"],
        "capacity": normalized["capacity"],
        "network": {**normalized["network"], **resolved},
        "gpu": normalized["gpu"],
        "backup": normalized["backup"],
        "deletion_protection": normalized["lifecycle"]["deletion_protection"],
        "release_channel": catalog.get("default_release_channel", "REGULAR"),
        "iam_principal_type": os.environ.get("IAM_PRINCIPAL_TYPE", "group"),
        "enable_google_groups_rbac": os.environ.get("ENABLE_GOOGLE_GROUPS_RBAC", "true").lower() == "true",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()

    try:
        result = render(load(args.request), args.repository_root)
    except (OSError, yaml.YAMLError, ValueError, ValidationError, RequestValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
