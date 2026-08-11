#!/usr/bin/env python3
"""Validate every request and detect repository-wide ownership conflicts."""

from __future__ import annotations

import argparse
import ipaddress
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.service import RequestValidationError  # noqa: E402
from scripts.validate_request import load_document, validate  # noqa: E402

NETWORK_KEYS = ("node_cidr", "pod_cidr", "service_cidr", "control_plane_cidr")
NAME_KEYS = ("subnet_name", "pod_range_name", "service_range_name")


@dataclass(frozen=True)
class RequestRecord:
    path: Path
    name: str
    project_id: str
    environment: str
    networks: dict[str, ipaddress.IPv4Network]
    resource_names: dict[str, str]


def discover_requests(request_root: Path) -> list[Path]:
    return sorted(path for path in request_root.glob("*/*.yaml") if path.is_file())


def parse_record(path: Path, repository_root: Path) -> RequestRecord:
    request, _ = validate(path, repository_root)
    document = load_document(path)
    metadata = document.get("metadata", {})
    resolved = document.get("resolved", {}).get("network", {})

    metadata_name = metadata.get("name", request.name)
    if metadata_name != request.name:
        raise ValueError(
            f"{path}: metadata.name {metadata_name!r} does not match spec.name {request.name!r}"
        )
    if path.stem != request.name:
        raise ValueError(f"{path}: filename must be {request.name}.yaml")
    if path.parent.name != request.environment.value:
        raise ValueError(
            f"{path}: directory {path.parent.name!r} does not match environment "
            f"{request.environment.value!r}"
        )

    missing_networks = [key for key in NETWORK_KEYS if not resolved.get(key)]
    missing_names = [key for key in NAME_KEYS if not resolved.get(key)]
    if missing_networks or missing_names:
        missing = ", ".join(missing_networks + missing_names)
        raise ValueError(f"{path}: resolved.network is missing {missing}")

    networks: dict[str, ipaddress.IPv4Network] = {}
    for key in NETWORK_KEYS:
        try:
            network = ipaddress.ip_network(resolved[key], strict=True)
        except ValueError as exc:
            raise ValueError(f"{path}: invalid resolved {key}: {resolved[key]}") from exc
        if not isinstance(network, ipaddress.IPv4Network):
            raise ValueError(f"{path}: resolved {key} must be IPv4")
        networks[key] = network

    return RequestRecord(
        path=path,
        name=request.name,
        project_id=request.project_id,
        environment=request.environment.value,
        networks=networks,
        resource_names={key: str(resolved[key]) for key in NAME_KEYS},
    )


def _duplicates(records: list[RequestRecord], attribute: str) -> list[str]:
    owners: dict[str, list[Path]] = {}
    for record in records:
        value = str(getattr(record, attribute))
        owners.setdefault(value, []).append(record.path)
    return [
        f"duplicate {attribute} {value!r}: {', '.join(str(path) for path in paths)}"
        for value, paths in owners.items()
        if len(paths) > 1
    ]


def validate_records(paths: list[Path], repository_root: Path) -> tuple[list[RequestRecord], list[str]]:
    records: list[RequestRecord] = []
    errors: list[str] = []

    for path in paths:
        try:
            records.append(parse_record(path, repository_root))
        except (ValueError, ValidationError, RequestValidationError, yaml.YAMLError) as exc:
            errors.append(str(exc))

    errors.extend(_duplicates(records, "name"))
    errors.extend(_duplicates(records, "project_id"))

    for key in NAME_KEYS:
        owners: dict[str, list[Path]] = {}
        for record in records:
            owners.setdefault(record.resource_names[key], []).append(record.path)
        for value, owner_paths in owners.items():
            if len(owner_paths) > 1:
                errors.append(
                    f"duplicate resolved {key} {value!r}: "
                    + ", ".join(str(path) for path in owner_paths)
                )

    allocations: list[tuple[Path, str, ipaddress.IPv4Network]] = []
    for record in records:
        for key, network in record.networks.items():
            allocations.append((record.path, key, network))

    for index, (left_path, left_key, left_network) in enumerate(allocations):
        for right_path, right_key, right_network in allocations[index + 1 :]:
            if left_path == right_path:
                continue
            if left_network.overlaps(right_network):
                errors.append(
                    f"overlapping allocations: {left_path} {left_key}={left_network} and "
                    f"{right_path} {right_key}={right_network}"
                )

    return records, errors


def validate_request_set(request_root: Path, repository_root: Path) -> list[RequestRecord]:
    paths = discover_requests(request_root)
    records, errors = validate_records(paths, repository_root)
    if errors:
        raise ValueError("\n".join(errors))
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--request-root",
        type=Path,
        default=REPOSITORY_ROOT / "requests",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
    )
    args = parser.parse_args()

    try:
        records = validate_request_set(args.request_root, args.repository_root)
    except ValueError as exc:
        for line in str(exc).splitlines():
            print(f"ERROR: {line}", file=sys.stderr)
        return 1

    print(f"VALID SET: {len(records)} request(s), no duplicate projects or overlapping allocations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
