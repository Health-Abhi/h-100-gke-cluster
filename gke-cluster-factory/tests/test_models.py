from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import ClusterRequestCreate


def test_valid_request_parses(valid_request: dict) -> None:
    request = ClusterRequestCreate.model_validate(valid_request)
    assert request.name == "payments-prod-usw1"
    assert request.owner.team == "payments"
    assert request.gpu.enabled is False


def test_invalid_cluster_name_is_rejected(valid_request: dict) -> None:
    valid_request["name"] = "Not Valid"
    with pytest.raises(ValidationError):
        ClusterRequestCreate.model_validate(valid_request)


def test_reservation_requires_name(valid_request: dict) -> None:
    valid_request["blueprint"] = "standard-prod-h100-v1"
    valid_request["gpu"] = {
        "enabled": True,
        "model": "nvidia-h100-80gb",
        "machine_type": "a3-highgpu-8g",
        "accelerator_count": 8,
        "minimum_nodes": 1,
        "maximum_nodes": 2,
        "zones": ["us-west1-a"],
        "provisioning_model": "reservation",
    }
    with pytest.raises(ValidationError):
        ClusterRequestCreate.model_validate(valid_request)


def test_public_control_plane_requires_authorized_cidr(valid_request: dict) -> None:
    valid_request["network"]["private_endpoint_only"] = False
    valid_request["network"]["authorized_cidrs"] = []
    with pytest.raises(ValidationError):
        ClusterRequestCreate.model_validate(valid_request)


def test_public_control_plane_accepts_and_normalizes_ipv4_cidr(valid_request: dict) -> None:
    valid_request["network"]["private_endpoint_only"] = False
    valid_request["network"]["authorized_cidrs"] = ["203.0.113.0/24", "198.51.100.10/32"]
    request = ClusterRequestCreate.model_validate(valid_request)
    assert request.network.authorized_cidrs == ["203.0.113.0/24", "198.51.100.10/32"]


def test_invalid_authorized_cidr_is_rejected(valid_request: dict) -> None:
    valid_request["network"]["private_endpoint_only"] = False
    valid_request["network"]["authorized_cidrs"] = ["203.0.113.7/24"]
    with pytest.raises(ValidationError):
        ClusterRequestCreate.model_validate(valid_request)
