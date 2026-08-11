from __future__ import annotations

import pytest

from app.config import Settings
from app.models import ClusterRequestCreate
from app.service import ClusterFactoryService, RequestValidationError


def service(repository_root):
    return ClusterFactoryService(Settings(_env_file=None, root_dir=repository_root, storage_mode="local"))


def test_production_guardrails(repository_root, valid_request: dict) -> None:
    valid_request["lifecycle"]["deletion_protection"] = False
    request = ClusterRequestCreate.model_validate(valid_request)
    with pytest.raises(RequestValidationError, match="deletion protection"):
        service(repository_root).validate(request)


def test_profile_adds_standard_labels(repository_root, valid_request: dict) -> None:
    request = ClusterRequestCreate.model_validate(valid_request)
    result = service(repository_root).validate(request)
    assert result.valid is True
    assert result.normalized["labels"]["managed-by"] == "gke-cluster-factory"
    assert result.normalized["labels"]["cost-center"] == "cc-1042"


def test_h100_profile_accepts_reservation(repository_root, valid_request: dict) -> None:
    valid_request["blueprint"] = "standard-prod-h100-v1"
    valid_request["gpu"] = {
        "enabled": True,
        "model": "nvidia-h100-80gb",
        "machine_type": "a3-highgpu-8g",
        "accelerator_count": 8,
        "minimum_nodes": 1,
        "maximum_nodes": 4,
        "zones": ["us-west1-a", "us-west1-b"],
        "provisioning_model": "reservation",
        "reservation_name": "payments-h100-prod",
    }
    request = ClusterRequestCreate.model_validate(valid_request)
    result = service(repository_root).validate(request)
    assert result.valid is True
