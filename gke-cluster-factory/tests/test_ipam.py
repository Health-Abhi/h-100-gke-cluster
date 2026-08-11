from __future__ import annotations

from app.ipam import allocate_network

CONFIG = {
    "pools": {
        "nodes": {"cidr": "10.64.0.0/16", "allocation_prefix": 24},
        "pods": {"cidr": "10.128.0.0/12", "allocation_prefix": 16},
        "services": {"cidr": "172.20.0.0/16", "allocation_prefix": 20},
        "control_planes": {"cidr": "172.24.0.0/16", "allocation_prefix": 28},
    }
}


def test_allocations_do_not_overlap() -> None:
    first = allocate_network("first-cluster", [], CONFIG)
    records = [{"resolved": {"network": first.model_dump()}}]
    second = allocate_network("second-cluster", records, CONFIG)

    assert first.node_cidr != second.node_cidr
    assert first.pod_cidr != second.pod_cidr
    assert first.service_cidr != second.service_cidr
    assert first.control_plane_cidr != second.control_plane_cidr


def test_resource_names_include_stable_hash() -> None:
    first = allocate_network("payments-application-production-west", [], CONFIG)
    second = allocate_network("payments-application-preview-west", [], CONFIG)

    assert first.subnet_name != second.subnet_name
    assert len(first.subnet_name) <= 63
    repeated = allocate_network("payments-application-production-west", [], CONFIG)
    assert first.subnet_name == repeated.subnet_name
