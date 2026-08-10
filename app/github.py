from __future__ import annotations

import base64
import re
from datetime import UTC, datetime
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

    async def list_pending_pull_requests(self) -> list[dict[str, Any]]:
        """Requests that have an open PR (not yet merged to the default branch)."""
        pulls = await self._request(
            "GET",
            f"{self.repo_path}/pulls",
            params={"state": "open", "base": self.default_branch, "per_page": 100},
        )
        records: list[dict[str, Any]] = []
        for pull in pulls:
            head_ref = pull.get("head", {}).get("ref", "")
            if not head_ref.startswith("cluster-request/"):
                continue
            head_sha = pull.get("head", {}).get("sha")
            files = await self._request(
                "GET",
                f"{self.repo_path}/pulls/{pull['number']}/files",
                params={"per_page": 100},
            )
            for changed in files:
                path = changed.get("filename", "")
                if not re.fullmatch(r"requests/(dev|test|stage|prod)/[^/]+\.yaml", path):
                    continue
                if changed.get("status") == "removed":
                    continue
                content = await self._request(
                    "GET",
                    f"{self.repo_path}/contents/{path}",
                    params={"ref": head_sha},
                )
                decoded = base64.b64decode(content["content"]).decode("utf-8")
                try:
                    record = yaml.safe_load(decoded)
                except yaml.YAMLError:
                    continue
                if isinstance(record, dict):
                    record["_path"] = path
                    status = record.setdefault("status", {}) or {}
                    status["phase"] = "PENDING_REVIEW"
                    status["pull_request_url"] = pull.get("html_url")
                    record["status"] = status
                    records.append(record)
        return records

    async def create_request_pull_request(
        self,
        request_path: str,
        yaml_text: str,
        cluster_name: str,
        actor: str,
    ) -> str:
        base_ref = await self._request(
            "GET",
            f"{self.repo_path}/git/ref/heads/{self.default_branch}",
        )
        base_sha = base_ref["object"]["sha"]
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        branch = f"cluster-request/{cluster_name}-{timestamp}"

        await self._request(
            "POST",
            f"{self.repo_path}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        encoded = base64.b64encode(yaml_text.encode("utf-8")).decode("ascii")
        await self._request(
            "PUT",
            f"{self.repo_path}/contents/{request_path}",
            json={
                "message": f"request: create GKE cluster {cluster_name}",
                "content": encoded,
                "branch": branch,
                "committer": {
                    "name": "GKE Cluster Factory",
                    "email": "gke-cluster-factory@users.noreply.github.com",
                },
            },
        )
        pull = await self._request(
            "POST",
            f"{self.repo_path}/pulls",
            json={
                "title": f"GKE cluster request: {cluster_name}",
                "head": branch,
                "base": self.default_branch,
                "body": (
                    f"Cluster request created by `{actor}` through the self-service portal.\n\n"
                    "The request validation, policy, quota preflight, and Terraform plan "
                    "workflows must pass before merge."
                ),
                "maintainer_can_modify": True,
            },
        )
        return pull["html_url"]