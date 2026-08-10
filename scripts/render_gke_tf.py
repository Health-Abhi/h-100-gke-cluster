#!/usr/bin/env python3
"""Render a validated cluster request as a standalone gke.tf module file.

This is a companion to render_tfvars.py. Where render_tfvars.py produces a
JSON var-file consumed by the shared terraform/cluster root module,
this script produces a small, human-readable Terraform file (gke.tf) that
calls a reusable GKE module directly with the same resolved values. The
file is written into its own per-cluster folder:

    clusters/<project_id>_<cluster_name>/gke.tf

That folder is what .github/workflows/publish-gke-tf.yml later copies into
the nonprod branch of the downstream GitOps repository.

Usage:
    scripts/render_gke_tf.py requests/dev/my-cluster.yaml
    scripts/render_gke_tf.py requests/dev/my-cluster.yaml --clusters-dir clusters
    scripts/render_gke_tf.py requests/dev/my-cluster.yaml --module-source git::https://example.com/gke.git//modules/gke?ref=v1.0.0
"""

from __future__ import annotations

import argparse
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

# Placeholder module source used until a real module registry/git source is
# supplied via --module-source or the GKE_MODULE_SOURCE environment variable.
DEFAULT_MODULE_SOURCE = "TODO-SET-GKE-MODULE-SOURCE"


def load(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Request must be a YAML mapping")
    return document


def folder_name(project_id: str, cluster_name: str) -> str:
    """(project)_(cluster_name), matching the layout the publish workflow expects."""
    return f"{project_id}_{cluster_name}"


def build_values(document: dict[str, Any], root: Path) -> dict[str, Any]:
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
    network = normalized["network"]
    capacity = normalized["capacity"]

    return {
        "cluster_name": request.name,
        "project_id": request.project_id,
        "region": request.region,
        "node_locations": node_locations,
        "environment": request.environment.value,
        "blueprint": request.blueprint,
        "system_machine_type": profile["system_machine_type"],
        "general_machine_type": profile["general_machine_type"],
        "capacity": {
            "system_min_nodes": capacity["system_min_nodes"],
            "system_max_nodes": capacity["system_max_nodes"],
            "general_min_nodes": capacity["general_min_nodes"],
            "general_max_nodes": capacity["general_max_nodes"],
            "max_pods_per_node": capacity["max_pods_per_node"],
        },
        "network": {
            "mode": network.get("mode"),
            "host_project_id": network.get("host_project_id") or request.project_id,
            "network_name": network.get("network_name"),
            "create_nat": network.get("create_nat"),
            "private_endpoint_only": network.get("private_endpoint_only"),
            "node_cidr": resolved["node_cidr"],
            "pod_cidr": resolved["pod_cidr"],
            "service_cidr": resolved["service_cidr"],
            "control_plane_cidr": resolved["control_plane_cidr"],
            "subnet_name": resolved["subnet_name"],
            "pod_range_name": resolved["pod_range_name"],
            "service_range_name": resolved["service_range_name"],
        },
        "deletion_protection": normalized["lifecycle"]["deletion_protection"],
        "release_channel": catalog.get("default_release_channel", "REGULAR"),
        "labels": normalized.get("labels", {}),
    }


# -- minimal HCL rendering ---------------------------------------------------


def _hcl_value(value: Any, indent: int) -> str:
    pad = "  " * indent
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        items = ",\n".join(f"{pad}  {_hcl_value(item, indent + 1)}" for item in value)
        return f"[\n{items}\n{pad}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = []
        for key, item in value.items():
            lines.append(f"{pad}  {_hcl_key(key)} = {_hcl_value(item, indent + 1)}")
        return "{\n" + "\n".join(lines) + f"\n{pad}}}"
    raise TypeError(f"Unsupported value for HCL rendering: {value!r}")


def _hcl_key(key: str) -> str:
    import re as _re

    if _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return key
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_gke_tf(values: dict[str, Any], module_source: str) -> str:
    header = (
        "# Generated by scripts/render_gke_tf.py — do not edit by hand.\n"
        "# Regenerate from the source cluster request YAML instead.\n\n"
    )
    body_lines = [f'  source = "{module_source}"', ""]
    ordered_top_level = (
        "project_id",
        "cluster_name",
        "region",
        "node_locations",
        "environment",
        "blueprint",
        "system_machine_type",
        "general_machine_type",
        "capacity",
        "network",
        "deletion_protection",
        "release_channel",
        "labels",
    )
    for key in ordered_top_level:
        body_lines.append(f"  {_hcl_key(key)} = {_hcl_value(values[key], 1)}")
    body = "\n".join(body_lines)
    return header + 'module "gke" {\n' + body + "\n}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--clusters-dir",
        type=Path,
        default=None,
        help="Root folder that per-cluster folders are created under (default: <repository-root>/clusters)",
    )
    parser.add_argument(
        "--module-source",
        default=os.environ.get("GKE_MODULE_SOURCE", DEFAULT_MODULE_SOURCE),
        help="Terraform module source for the generated gke.tf (env: GKE_MODULE_SOURCE)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Explicit output file path, overriding the clusters/<project>_<cluster>/gke.tf layout",
    )
    args = parser.parse_args()

    try:
        document = load(args.request)
        values = build_values(document, args.repository_root)
        content = render_gke_tf(values, args.module_source)
    except (OSError, yaml.YAMLError, ValueError, ValidationError, RequestValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.output:
        output_path = args.output
    else:
        clusters_dir = args.clusters_dir or (args.repository_root / "clusters")
        folder = folder_name(values["project_id"], values["cluster_name"])
        output_path = clusters_dir / folder / "gke.tf"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
