from __future__ import annotations

from scripts.render_tfvars import load, render


def test_example_request_renders(repository_root, monkeypatch) -> None:
    monkeypatch.setenv("GKE_SECURITY_GROUP", "gke-security@example.org")
    monkeypatch.setenv("PLATFORM_ADMIN_GROUP", "platform-admins@example.org")
    path = repository_root / "requests" / "prod" / "payments-ml-prod-usw1.yaml"
    result = render(load(path), repository_root)
    assert result["cluster_name"] == "payments-ml-prod-usw1"
    assert result["network"]["pod_range_name"] == "pods-payments-ml-prod-9d9e93"
    assert result["gpu"]["accelerator_count"] == 8
    assert result["gke_security_group"] == "gke-security@example.org"
    assert result["platform_admin_group"] == "platform-admins@example.org"
