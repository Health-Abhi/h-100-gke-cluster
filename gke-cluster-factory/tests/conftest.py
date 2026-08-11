from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def valid_request() -> dict:
    return {
        "name": "payments-prod-usw1",
        "project_id": "prj-payments-prod",
        "blueprint": "standard-prod-v1",
        "environment": "prod",
        "region": "us-west1",
        "owner": {
            "team": "payments",
            "google_group": "gcp-payments@example.com",
            "cost_center": "cc-1042",
            "technical_contact": "platform@example.com",
        },
        "workload": {
            "data_classification": "confidential",
            "exposure": "internal",
            "description": "Payments services",
        },
        "capacity": {
            "system_min_nodes": 3,
            "system_max_nodes": 9,
            "general_min_nodes": 3,
            "general_max_nodes": 60,
            "max_pods_per_node": 64,
        },
        "gpu": {"enabled": False},
        "availability": {
            "tier": "regional-ha",
            "application_minimum_replicas": 3,
        },
        "backup": {
            "tier": "gold",
            "retention_days": 90,
            "delete_lock_days": 7,
            "target_rpo_minutes": 60,
            "include_volume_data": True,
            "include_secrets": True,
        },
        "network": {
            "mode": "dedicated",
            "network_name": "gke-platform",
            "create_nat": True,
            "private_endpoint_only": True,
            "authorized_cidrs": [],
        },
        "lifecycle": {"deletion_protection": True},
        "labels": {"application": "payments"},
    }


@pytest.fixture
def copy_request(valid_request: dict):
    return deepcopy(valid_request)
