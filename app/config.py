from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FACTORY_",
        case_sensitive=False,
        extra="ignore",
    )

    root_dir: Path = Field(default_factory=lambda: Path.cwd())
    request_dir: Path | None = None
    profile_file: Path | None = None
    ipam_file: Path | None = None

    storage_mode: Literal["local", "github"] = "local"
    api_token: str | None = None
    allowed_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]

    github_token: str | None = None
    github_owner: str | None = None
    github_repository: str | None = None
    github_default_branch: str = "main"
    github_api_url: str = "https://api.github.com"

    log_level: str = "INFO"
    environment: str = "development"

    # Local provisioning (portal-triggered "Provision" button). Only used in
    # storage_mode=local, as a convenience alternative to running the
    # GitHub Actions plan/apply pipeline by hand.
    enable_local_provisioning: bool = False
    terraform_binary: str = "terraform"
    gcloud_binary: str = "gcloud"
    tf_state_bucket: str | None = None
    create_cluster_projects: bool = False
    cluster_project_parent: str | None = None
    billing_account: str | None = None
    gke_module_source: str | None = None
    gke_security_group: str | None = None
    platform_admin_group: str | None = None
    iam_principal_type: str = "group"
    enable_google_groups_rbac: bool = True
    skip_preflight: bool = False

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def resolved_request_dir(self) -> Path:
        return self.request_dir or self.root_dir / "requests"

    def resolved_profile_file(self) -> Path:
        return self.profile_file or self.root_dir / "config" / "profiles.yaml"

    def resolved_ipam_file(self) -> Path:
        return self.ipam_file or self.root_dir / "config" / "ipam.yaml"

    def validate_github_settings(self) -> None:
        if self.storage_mode != "github":
            return
        missing = [
            name
            for name, value in {
                "FACTORY_GITHUB_TOKEN": self.github_token,
                "FACTORY_GITHUB_OWNER": self.github_owner,
                "FACTORY_GITHUB_REPOSITORY": self.github_repository,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"GitHub storage mode requires: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_github_settings()
    return settings
