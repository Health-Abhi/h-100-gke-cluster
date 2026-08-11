#!/usr/bin/env python3
"""Render a validated cluster request as a standalone gke.tf module file.

This is a thin CLI wrapper around app.gke_tf (the same code the portal uses
to write clusters/<project_id>_<cluster_name>/gke.tf at request-submission
time). This script is what CI (.github/workflows/request-apply.yml) and the
portal's local-provisioning path (app/provisioner.py) call to (re)generate
the file once real infrastructure values are known.

Usage:
    scripts/render_gke_tf.py requests/dev/my-cluster.yaml
    scripts/render_gke_tf.py requests/dev/my-cluster.yaml --clusters-dir clusters
    scripts/render_gke_tf.py requests/dev/my-cluster.yaml --module-source git::https://example.com/gke.git//modules/gke?ref=v1.0.0
    scripts/render_gke_tf.py requests/dev/my-cluster.yaml --create-project --project-parent folders/123 --billing-account 01AB-CD23-EF45
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

from app.gke_tf import DEFAULT_MODULE_SOURCE, write_gke_tf  # noqa: E402
from app.service import RequestValidationError  # noqa: E402


def load(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Request must be a YAML mapping")
    return document


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
    parser.add_argument(
        "--create-project",
        action="store_true",
        default=os.environ.get("CREATE_CLUSTER_PROJECTS", "false").lower() == "true",
        help=(
            "Include a google_project resource (project name, folder/org id, billing account) "
            "in the generated gke.tf so it can create its own project (env: CREATE_CLUSTER_PROJECTS)"
        ),
    )
    parser.add_argument(
        "--project-parent",
        default=os.environ.get("CLUSTER_PROJECT_PARENT"),
        help="Folder or org the new project is created under, e.g. folders/123456789 (env: CLUSTER_PROJECT_PARENT)",
    )
    parser.add_argument(
        "--billing-account",
        default=os.environ.get("BILLING_ACCOUNT"),
        help="Billing account ID linked to the new project (env: BILLING_ACCOUNT)",
    )
    args = parser.parse_args()

    try:
        document = load(args.request)
        output_path = write_gke_tf(
            document,
            args.repository_root,
            module_source=args.module_source,
            create_project=args.create_project,
            project_parent=args.project_parent,
            billing_account=args.billing_account,
            clusters_dir=args.clusters_dir,
            output=args.output,
        )
    except (OSError, yaml.YAMLError, ValueError, ValidationError, RequestValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
