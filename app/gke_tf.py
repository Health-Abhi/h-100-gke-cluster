"""Shared logic for rendering a validated cluster request as a standalone
gke.tf module file.

This is used by two callers:
- scripts/render_gke_tf.py (CLI, also used by the CI pipelines)
- app/service.py (called directly at portal submission time, so the file
  shows up immediately instead of only after a full terraform apply)

Output layout:

    clusters/<project_id>_<cluster_name>/gke.tf

That folder is what .github/workflows/publish-gke-tf.yml later copies into
the nonprod branch of the downstream GitOps repository.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings
from app.models import ClusterRequestCreate

# Placeholder module source used until a real module registry/git source is
# supplied via --module-source, the GKE_MODULE_SOURCE environment variable,
# or FACTORY_GKE_MODULE_SOURCE in .env.
DEFAULT_MODULE_SOURCE = "TODO-SET-GKE-MODULE-SOURCE"


def folder_name(project_id: str, cluster_name: str) -> str:
    """(project)_(cluster_name), matching the layout the publish workflow expects."""
    return f"{project_id}_{cluster_name}"


def build_values(document: dict[str, Any], root: Path) -> dict[str, Any]:
    from app.service import ClusterFactoryService  # local import: avoids a circular import

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
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return key
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def split_parent(project_parent: str) -> tuple[str | None, str | None]:
    """Return (folder_id, org_id) parsed out of 'folders/123' or 'organizations/456'."""
    if not project_parent:
        return None, None
    kind, _, parent_id = project_parent.partition("/")
    if kind == "folders" and parent_id:
        return parent_id, None
    if kind == "organizations" and parent_id:
        return None, parent_id
    raise ValueError(
        f"project_parent must look like 'folders/<id>' or 'organizations/<id>', got: {project_parent!r}"
    )


def render_project_block(
    *, project_id: str, cluster_name: str, project_parent: str, billing_account: str
) -> str:
    """Mirror the google_project resource in terraform/cluster/main.tf, so the
    published gke.tf can create its own project/folder placement + billing
    linkage instead of assuming the project already exists."""
    if not project_parent or not billing_account:
        raise ValueError("project_parent and billing_account are required when create_project is set")
    folder_id, org_id = split_parent(project_parent)

    lines = [
        'resource "google_project" "cluster" {',
        f"  project_id      = {_hcl_value(project_id, 1)}",
        f"  name            = {_hcl_value(cluster_name, 1)}",
        f"  billing_account = {_hcl_value(billing_account, 1)}",
        f"  folder_id       = {_hcl_value(folder_id, 1)}",
        f"  org_id          = {_hcl_value(org_id, 1)}",
        "}\n",
    ]
    return "\n".join(lines)


def render_gke_tf(
    values: dict[str, Any],
    module_source: str,
    *,
    create_project: bool = False,
    project_parent: str | None = None,
    billing_account: str | None = None,
) -> str:
    header = (
        "# Generated by scripts/render_gke_tf.py — do not edit by hand.\n"
        "# Regenerate from the source cluster request YAML instead.\n\n"
    )

    project_block = ""
    if create_project:
        project_block = (
            render_project_block(
                project_id=values["project_id"],
                cluster_name=values["cluster_name"],
                project_parent=project_parent or "",
                billing_account=billing_account or "",
            )
            + "\n"
        )

    body_lines = [f'  source = "{module_source}"', ""]
    if create_project:
        body_lines.append("  depends_on = [google_project.cluster]")
        body_lines.append("")
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
    return header + project_block + 'module "gke" {\n' + body + "\n}\n"


def render_from_document(
    document: dict[str, Any],
    root: Path,
    *,
    module_source: str = DEFAULT_MODULE_SOURCE,
    create_project: bool = False,
    project_parent: str | None = None,
    billing_account: str | None = None,
) -> tuple[str, str]:
    """Build gke.tf content for a request document.

    Returns (relative_path, content), where relative_path is
    'clusters/<project_id>_<cluster_name>/gke.tf'.
    """
    values = build_values(document, root)
    content = render_gke_tf(
        values,
        module_source,
        create_project=create_project,
        project_parent=project_parent,
        billing_account=billing_account,
    )
    folder = folder_name(values["project_id"], values["cluster_name"])
    relative_path = f"clusters/{folder}/gke.tf"
    return relative_path, content


def write_gke_tf(
    document: dict[str, Any],
    root: Path,
    *,
    module_source: str = DEFAULT_MODULE_SOURCE,
    create_project: bool = False,
    project_parent: str | None = None,
    billing_account: str | None = None,
    clusters_dir: Path | None = None,
    output: Path | None = None,
) -> Path:
    """Render and write gke.tf to disk, returning the path written."""
    relative_path, content = render_from_document(
        document,
        root,
        module_source=module_source,
        create_project=create_project,
        project_parent=project_parent,
        billing_account=billing_account,
    )
    if output:
        output_path = output
    else:
        base = clusters_dir or (root / "clusters")
        output_path = base / Path(relative_path).relative_to("clusters")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
