from __future__ import annotations

import importlib
import shutil

from fastapi.testclient import TestClient


def test_local_api_creates_request(tmp_path, monkeypatch, repository_root, valid_request: dict) -> None:
    shutil.copytree(repository_root / "config", tmp_path / "config")
    (tmp_path / "requests").mkdir()

    monkeypatch.setenv("FACTORY_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("FACTORY_STORAGE_MODE", "local")

    import app.config as config

    config.get_settings.cache_clear()
    import app.main as main

    importlib.reload(main)

    with TestClient(main.app) as client:
        catalog = client.get("/api/v1/catalog")
        assert catalog.status_code == 200
        response = client.post("/api/v1/requests", json=valid_request)
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "LOCAL_CREATED"
        listed = client.get("/api/v1/requests")
        assert listed.status_code == 200
        assert listed.json()[0]["name"] == valid_request["name"]

    assert (tmp_path / "requests" / "prod" / f"{valid_request['name']}.yaml").exists()
    config.get_settings.cache_clear()


def test_local_api_rejects_duplicate_project(
    tmp_path, monkeypatch, repository_root, valid_request: dict
) -> None:
    shutil.copytree(repository_root / "config", tmp_path / "config")
    (tmp_path / "requests").mkdir()

    monkeypatch.setenv("FACTORY_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("FACTORY_STORAGE_MODE", "local")

    import app.config as config

    config.get_settings.cache_clear()
    import app.main as main

    importlib.reload(main)

    with TestClient(main.app) as client:
        first = client.post("/api/v1/requests", json=valid_request)
        assert first.status_code == 201, first.text

        second_request = dict(valid_request)
        second_request["name"] = "payments-secondary-prod-usw1"
        second = client.post("/api/v1/requests", json=second_request)
        assert second.status_code == 422
        assert "already owned" in second.text

    config.get_settings.cache_clear()
