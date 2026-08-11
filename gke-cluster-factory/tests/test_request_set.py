from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.validate_request_set import validate_request_set


def test_request_set_accepts_example(repository_root: Path) -> None:
    records = validate_request_set(repository_root / "requests", repository_root)
    assert [record.name for record in records] == ["payments-ml-prod-usw1"]


def test_request_set_rejects_duplicate_project(tmp_path: Path, repository_root: Path) -> None:
    request_root = tmp_path / "requests"
    prod = request_root / "prod"
    prod.mkdir(parents=True)

    original = yaml.safe_load((repository_root / "requests/prod/payments-ml-prod-usw1.yaml").read_text())
    first = deepcopy(original)
    second = deepcopy(original)

    first["metadata"]["name"] = "first-prod-usw1"
    first["spec"]["name"] = "first-prod-usw1"
    first["resolved"]["network"].update(
        {
            "subnet_name": "snet-first-prod-usw1-a1b2c3",
            "pod_range_name": "pods-first-prod-usw1-a1b2c3",
            "service_range_name": "svc-first-prod-usw1-a1b2c3",
        }
    )

    second["metadata"]["name"] = "second-prod-usw1"
    second["spec"]["name"] = "second-prod-usw1"
    second["resolved"]["network"].update(
        {
            "node_cidr": "10.64.1.0/24",
            "pod_cidr": "10.129.0.0/16",
            "service_cidr": "172.20.16.0/20",
            "control_plane_cidr": "172.24.0.16/28",
            "subnet_name": "snet-second-prod-usw1-d4e5f6",
            "pod_range_name": "pods-second-prod-usw1-d4e5f6",
            "service_range_name": "svc-second-prod-usw1-d4e5f6",
        }
    )

    (prod / "first-prod-usw1.yaml").write_text(yaml.safe_dump(first, sort_keys=False))
    (prod / "second-prod-usw1.yaml").write_text(yaml.safe_dump(second, sort_keys=False))

    with pytest.raises(ValueError, match="duplicate project_id"):
        validate_request_set(request_root, repository_root)
