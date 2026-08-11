from __future__ import annotations

import base64
import re
from typing import Any

import httpx
import yaml


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(
        self,
        token: str,
        owner: str,
        repository: str,
        default_branch: str = "main",
        api_url: str = "https://api.github.com",
    ) -> None:
        self.owner = owner
        self.repository = repository
        self.default_branch = default_branch
        self.api_url = api_url.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "gke-cluster-factory",
            },
        )

    @property
    def repo_path(self) -> str:
        return f"/repos/{self.owner}/{self.repository}"

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.client.request(method, f"{self.api_url}{path}", **kwargs)
        if response.status_code >= 400:
            detail = response.text[:500]
            raise GitHubError(f"GitHub API {method} {path} failed: {response.status_code} {detail}")
        if response.status_code == 204:
            return None
        return response.json()

    async def list_request_records(self) -> list[dict[str, Any]]:
        tree = await self._request(
            "GET",
            f"{self.repo_path}/git/trees/{self.default_branch}",
            params={"recursive": "1"},
        )
        paths = [
            item["path"]
            for item in tree.get("tree", [])
            if item.get("type") == "blob"
            and re.fullmatch(r"requests/(dev|test|stage|prod)/[^/]+\.yaml", item.get("path", ""))
        ]
        records: list[dict[str, Any]] = []
        for path in paths[:500]:
            content = await self._request(
                "GET",
                f"{self.repo_path}/contents/{path}",
                params={"ref": self.default_branch},
            )
            decoded = base64.b64decode(content["content"]).decode("utf-8")
            try:
                record = yaml.safe_load(decoded)
            except yaml.YAMLError:
                continue
            if isinstance(record, dict):
                record["_path"] = path
                records.append(record)
        return records

    async def create_request_direct_commit(
        self,
        request_path: str,
        yaml_text: str,
        cluster_name: str,
        actor: str,
        extra_files: dict[str, str] | None = None,
    ) -> str:
        """Commit the request (and any extra files, e.g. gke.tf) straight onto
        the default branch - no branch is created and no pull request is
        opened. The push itself is what triggers request-plan.yml /
        request-apply.yml for this commit."""
        encoded = base64.b64encode(yaml_text.encode("utf-8")).decode("ascii")
        commit = await self._request(
            "PUT",
            f"{self.repo_path}/contents/{request_path}",
            json={
                "message": f"request: create GKE cluster {cluster_name} (by {actor})",
                "content": encoded,
                "branch": self.default_branch,
                "committer": {
                    "name": "GKE Cluster Factory",
                    "email": "gke-cluster-factory@users.noreply.github.com",
                },
            },
        )
        for extra_path, extra_text in (extra_files or {}).items():
            extra_encoded = base64.b64encode(extra_text.encode("utf-8")).decode("ascii")
            commit = await self._request(
                "PUT",
                f"{self.repo_path}/contents/{extra_path}",
                json={
                    "message": f"request: generate {extra_path} for {cluster_name}",
                    "content": extra_encoded,
                    "branch": self.default_branch,
                    "committer": {
                        "name": "GKE Cluster Factory",
                        "email": "gke-cluster-factory@users.noreply.github.com",
                    },
                },
            )
        return commit["commit"]["html_url"]