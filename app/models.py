from __future__ import annotations

import ipaddress
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

DNS_LABEL = re.compile(r"^[a-z](?:[a-z0-9-]{0,38}[a-z0-9])?$")
GCP_LABEL_VALUE = re.compile(r"^[a-z0-9_-]{1,63}$")


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGE = "stage"
    PROD = "prod"


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class Exposure(StrEnum):
    NONE = "none"
    INTERNAL = "internal"
    EXTERNAL = "external"


class BackupTier(StrEnum):
    NONE = "none"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class NetworkMode(StrEnum):
    DEDICATED = "dedicated"
    SHARED = "shared"


class ProvisioningModel(StrEnum):
    STANDARD = "standard"
    SPOT = "spot"
    FLEX_START = "flex-start"
    RESERVATION = "reservation"


class Owner(BaseModel):
    team: str = Field(min_length=2, max_length=40)
    google_group: EmailStr
    cost_center: str = Field(min_length=2, max_length=40)
    technical_contact: EmailStr | None = None

    @field_validator("team")
    @classmethod
    def normalize_team(cls, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "-")
        if not GCP_LABEL_VALUE.fullmatch(normalized):
            raise ValueError("team must use lowercase letters, numbers, hyphens, or underscores")
        return normalized


class Workload(BaseModel):
    data_classification: DataClassification = DataClassification.INTERNAL
    exposure: Exposure = Exposure.INTERNAL
    description: str = Field(default="", max_length=300)


class Capacity(BaseModel):
    system_min_nodes: int = Field(default=3, ge=1, le=30)
    system_max_nodes: int = Field(default=6, ge=1, le=60)
    general_min_nodes: int = Field(default=3, ge=0, le=100)
    general_max_nodes: int = Field(default=30, ge=1, le=1000)
    max_pods_per_node: int = Field(default=64, ge=8, le=256)

    @model_validator(mode="after")
    def validate_ranges(self) -> Capacity:
        if self.system_max_nodes < self.system_min_nodes:
            raise ValueError("system_max_nodes must be greater than or equal to system_min_nodes")
        if self.general_max_nodes < self.general_min_nodes:
            raise ValueError("general_max_nodes must be greater than or equal to general_min_nodes")
        return self


class GPU(BaseModel):
    enabled: bool = False
    model: str | None = None
    machine_type: str | None = None
    accelerator_count: int = Field(default=0, ge=0, le=16)
    minimum_nodes: int = Field(default=0, ge=0, le=100)
    maximum_nodes: int = Field(default=0, ge=0, le=1000)
    zones: list[str] = Field(default_factory=list, max_length=3)
    provisioning_model: ProvisioningModel = ProvisioningModel.STANDARD
    reservation_name: str | None = Field(default=None, max_length=63)

    @model_validator(mode="after")
    def validate_gpu(self) -> GPU:
        if not self.enabled:
            self.model = None
            self.machine_type = None
            self.accelerator_count = 0
            self.minimum_nodes = 0
            self.maximum_nodes = 0
            self.zones = []
            self.reservation_name = None
            return self

        required = {
            "model": self.model,
            "machine_type": self.machine_type,
            "accelerator_count": self.accelerator_count,
            "zones": self.zones,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"GPU configuration is missing: {', '.join(missing)}")
        if self.maximum_nodes < self.minimum_nodes:
            raise ValueError("GPU maximum_nodes must be greater than or equal to minimum_nodes")
        if self.provisioning_model == ProvisioningModel.RESERVATION and not self.reservation_name:
            raise ValueError("reservation_name is required when provisioning_model is reservation")
        return self


class Availability(BaseModel):
    tier: str = "regional-ha"
    application_minimum_replicas: int = Field(default=3, ge=1, le=50)
    secondary_region: str | None = None


class Backup(BaseModel):
    tier: BackupTier = BackupTier.NONE
    retention_days: int = Field(default=7, ge=1, le=365)
    delete_lock_days: int = Field(default=0, ge=0, le=90)
    target_rpo_minutes: int = Field(default=1440, ge=60, le=86400)
    include_volume_data: bool = True
    include_secrets: bool = True

    @model_validator(mode="after")
    def validate_retention(self) -> Backup:
        if self.delete_lock_days > self.retention_days:
            raise ValueError("delete_lock_days cannot exceed retention_days")
        return self


class Network(BaseModel):
    mode: NetworkMode = NetworkMode.DEDICATED
    host_project_id: str | None = None
    network_name: str = "gke-platform"
    create_nat: bool = True
    private_endpoint_only: bool = True
    authorized_cidrs: list[str] = Field(default_factory=list, max_length=25)

    @field_validator("authorized_cidrs")
    @classmethod
    def validate_authorized_cidrs(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            try:
                network = ipaddress.ip_network(value, strict=True)
            except ValueError as exc:
                raise ValueError(f"invalid authorized CIDR: {value}") from exc
            if not isinstance(network, ipaddress.IPv4Network):
                raise ValueError("authorized CIDRs must be IPv4 networks")
            normalized.append(str(network))
        return normalized

    @model_validator(mode="after")
    def validate_network(self) -> Network:
        if self.mode == NetworkMode.SHARED and not self.host_project_id:
            raise ValueError("host_project_id is required for Shared VPC mode")
        if not self.private_endpoint_only and not self.authorized_cidrs:
            raise ValueError("authorized_cidrs is required when the public control-plane endpoint is enabled")
        return self


class Lifecycle(BaseModel):
    deletion_protection: bool = True
    expiration_date: str | None = None


class ClusterRequestCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=3, max_length=40)
    project_id: str = Field(min_length=6, max_length=30)
    blueprint: str
    environment: Environment
    region: str = "us-west1"
    owner: Owner
    workload: Workload = Field(default_factory=Workload)
    capacity: Capacity = Field(default_factory=Capacity)
    gpu: GPU = Field(default_factory=GPU)
    availability: Availability = Field(default_factory=Availability)
    backup: Backup = Field(default_factory=Backup)
    network: Network = Field(default_factory=Network)
    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.lower()
        if not DNS_LABEL.fullmatch(value):
            raise ValueError(
                "name must be a lowercase DNS label, start with a letter, and be at most 40 characters"
            )
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        value = value.lower()
        if not re.fullmatch(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$", value):
            raise ValueError("project_id must be a valid Google Cloud project ID")
        return value

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if not re.fullmatch(r"^[a-z][a-z0-9_-]{0,62}$", key):
                raise ValueError(f"invalid label key: {key}")
            if item and not re.fullmatch(r"^[a-z0-9_-]{0,63}$", item):
                raise ValueError(f"invalid label value for {key}")
        return value


class ResolvedNetwork(BaseModel):
    node_cidr: str
    pod_cidr: str
    service_cidr: str
    control_plane_cidr: str
    subnet_name: str
    pod_range_name: str
    service_range_name: str


class ValidationResult(BaseModel):
    valid: bool
    warnings: list[str] = Field(default_factory=list)
    normalized: dict[str, Any] | None = None


class RequestSummary(BaseModel):
    name: str
    project_id: str
    environment: str
    region: str
    blueprint: str
    owner_team: str
    status: str
    created_at: str
    commit_url: str | None = None
    gpu_enabled: bool = False


class RequestSubmission(BaseModel):
    name: str
    status: str
    message: str
    request_path: str
    commit_url: str | None = None
    resolved_network: ResolvedNetwork


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
