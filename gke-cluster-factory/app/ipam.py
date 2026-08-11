from __future__ import annotations

import hashlib
import ipaddress
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from app.models import ResolvedNetwork


class IPAMError(RuntimeError):
    pass


def _extract_used_networks(records: Iterable[dict[str, Any]], key: str) -> set[ipaddress.IPv4Network]:
    used: set[ipaddress.IPv4Network] = set()
    for record in records:
        value = record.get("resolved", {}).get("network", {}).get(key)
        if value:
            try:
                used.add(ipaddress.ip_network(value))
            except ValueError:
                continue
    return used


def _next_subnet(pool_cidr: str, allocation_prefix: int, used: set[ipaddress.IPv4Network]) -> str:
    pool = ipaddress.ip_network(pool_cidr)
    if not isinstance(pool, ipaddress.IPv4Network):
        raise IPAMError("Only IPv4 pools are supported")
    if allocation_prefix < pool.prefixlen:
        raise IPAMError(f"Allocation /{allocation_prefix} is larger than pool {pool}")

    for candidate in pool.subnets(new_prefix=allocation_prefix):
        if candidate not in used:
            return str(candidate)
    raise IPAMError(f"IP pool exhausted: {pool}")


def load_ipam_config(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise IPAMError(f"IPAM file not found: {path}") from exc
    if "pools" not in data:
        raise IPAMError("IPAM configuration must contain pools")
    return data


def allocate_network(
    cluster_name: str,
    existing_records: Iterable[dict[str, Any]],
    config: dict[str, Any],
) -> ResolvedNetwork:
    records = list(existing_records)
    pools = config["pools"]

    def allocate(pool_name: str, record_key: str) -> str:
        pool = pools[pool_name]
        return _next_subnet(
            pool_cidr=pool["cidr"],
            allocation_prefix=int(pool["allocation_prefix"]),
            used=_extract_used_networks(records, record_key),
        )

    digest = hashlib.sha256(cluster_name.encode("utf-8")).hexdigest()[:6]
    safe_name = cluster_name[:17].rstrip("-")
    resource_suffix = f"{safe_name}-{digest}"
    return ResolvedNetwork(
        node_cidr=allocate("nodes", "node_cidr"),
        pod_cidr=allocate("pods", "pod_cidr"),
        service_cidr=allocate("services", "service_cidr"),
        control_plane_cidr=allocate("control_planes", "control_plane_cidr"),
        subnet_name=f"snet-{resource_suffix}",
        pod_range_name=f"pods-{resource_suffix}",
        service_range_name=f"svc-{resource_suffix}",
    )
