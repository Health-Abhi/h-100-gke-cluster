from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml

from app.catalog import CatalogError, get_profile, load_catalog
from app.config import Settings
from app.github import GitHubClient
from app.gke_tf import DEFAULT_MODULE_SOURCE, render_from_document
from app.ipam import allocate_network, load_ipam_config
from app.models import (
    BackupTier,
    ClusterRequestCreate,
    DataClassification,
    Environment,
    Exposure,
    ProvisioningModel,
    RequestSubmission,
    RequestSummary,
    ResolvedNetwork,
    ValidationResult,
    utc_now,
)
from app.provisioner import ProvisionJob, ProvisionManager
from app.repository import LocalRequestRepository


class RequestValidationError(ValueError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings or []


class ClusterFactoryService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.local_repository = LocalRequestRepository(settings.resolved_request_dir())
        self.github: GitHubClient | None = None
        if settings.storage_mode == "github":
            self.github = GitHubClient(
                token=settings.github_token or "",
                owner=settings.github_owner or "",
                repository=settings.github_repository or "",
                default_branch=settings.github_default_branch,
                api_url=settings.github_api_url,
            )
        self.provisioner = ProvisionManager(settings, settings.root_dir)

    async def close(self) -> None:
        if self.github:
            await self.github.close()

    def catalog(self) -> dict[str, Any]:
        return load_catalog(self.settings.resolved_profile_file())

    async def records(self) -> list[dict[str, Any]]:
        if self.github:
            merged = await self.github.list_request_records()
            existing_names = {item.get("metadata", {}).get("name") for item in merged}
            pending = await self.github.list_pending_pull_requests()
            for record in pending:
                if record.get("metadata", {}).get("name") in existing_names:
                    continue
                merged.append(record)
            return merged
        return self.local_repository.list_records()

    def validate(self, request: ClusterRequestCreate) -> ValidationResult:
        catalog = self.catalog()
        errors: list[str] = []
        warnings: list[str] = []
        try:
            profile = get_profile(catalog, request.blueprint)
        except CatalogError as exc:
            raise RequestValidationError([str(exc)]) from exc

        allowed_environments = profile.get("allowed_environments", [])
        if request.environment.value not in allowed_environments:
            errors.append(
                f"Blueprint {request.blueprint} does not allow environment {request.environment.value}"
            )

        allowed_regions = catalog.get("allowed_regions", ["us-west1"])
        if request.region not in allowed_regions:
            errors.append(f"Region {request.region} is not approved")

        if request.environment == Environment.PROD:
            if not request.lifecycle.deletion_protection:
                errors.append("Production clusters require deletion protection")
            if request.backup.tier == BackupTier.NONE:
                errors.append("Production clusters require a backup tier")
            if request.capacity.system_min_nodes < 3:
                errors.append("Production clusters require at least three system nodes")
            if request.capacity.general_min_nodes < 3:
                errors.append("Production clusters require at least three general nodes")
            if request.availability.application_minimum_replicas < 3:
                errors.append("Production availability requires at least three application replicas")

        if request.workload.data_classification == DataClassification.RESTRICTED:
            if request.workload.exposure == Exposure.EXTERNAL:
                errors.append("Restricted workloads cannot use external exposure")
            if not request.network.private_endpoint_only:
                errors.append("Restricted workloads require a private control-plane endpoint")

        profile_gpu = profile.get("gpu", {})
        if request.gpu.enabled:
            if not profile_gpu.get("allowed", False):
                errors.append(f"Blueprint {request.blueprint} does not permit GPU node pools")
            if request.gpu.model not in profile_gpu.get("models", []):
                errors.append(f"GPU model {request.gpu.model} is not approved for this blueprint")
            if request.gpu.machine_type not in profile_gpu.get("machine_types", []):
                errors.append(f"GPU machine type {request.gpu.machine_type} is not approved")
            invalid_zones = [zone for zone in request.gpu.zones if not zone.startswith(f"{request.region}-")]
            if invalid_zones:
                errors.append(f"GPU zones must belong to {request.region}: {', '.join(invalid_zones)}")
            if request.environment == Environment.PROD:
                if request.gpu.minimum_nodes < 1:
                    errors.append("Production H100 pools must keep at least one node available")
                if request.gpu.provisioning_model not in {
                    ProvisioningModel.RESERVATION,
                    ProvisioningModel.STANDARD,
                }:
                    errors.append("Production H100 pools cannot rely on Spot or Flex-start capacity")
                if request.gpu.provisioning_model == ProvisioningModel.STANDARD:
                    warnings.append(
                        "H100 on-demand capacity is not guaranteed; a reservation is strongly recommended"
                    )
        elif profile.get("requires_gpu", False):
            errors.append(f"Blueprint {request.blueprint} requires a GPU configuration")

        if request.network.mode.value == "shared" and request.network.create_nat:
            warnings.append(
                "In Shared VPC mode, confirm that one regional Cloud NAT is not already managed centrally"
            )

        if request.backup.tier == BackupTier.GOLD and request.backup.target_rpo_minutes > 240:
            warnings.append("Gold backup normally targets an RPO of four hours or less")

        if request.lifecycle.expiration_date is None and request.environment != Environment.PROD:
            warnings.append("Non-production clusters should normally have an expiration date")

        if errors:
            raise RequestValidationError(errors, warnings)

        normalized = request.model_dump(mode="json")
        normalized["labels"] = {
            **normalized.get("labels", {}),
            "environment": request.environment.value,
            "team": request.owner.team,
            "cost-center": request.owner.cost_center.lower().replace(" ", "-")[:63],
            "managed-by": "gke-cluster-factory",
        }
        return ValidationResult(valid=True, warnings=warnings, normalized=normalized)

    async def submit(self, request: ClusterRequestCreate, actor: str) -> RequestSubmission:
        validation = self.validate(request)
        existing = await self.records()
        if any(item.get("metadata", {}).get("name") == request.name for item in existing):
            raise RequestValidationError([f"A request named {request.name} already exists"])
        project_owner = next(
            (
                item.get("metadata", {}).get("name", "another request")
                for item in existing
                if item.get("spec", {}).get("project_id") == request.project_id
            ),
            None,
        )
        if project_owner:
            raise RequestValidationError(
                [f"Project ID {request.project_id} is already owned by request {project_owner}"]
            )

        ipam_config = load_ipam_config(self.settings.resolved_ipam_file())
        resolved_network = allocate_network(request.name, existing, ipam_config)
        record = self._build_record(request, validation, resolved_network, actor)
        yaml_text = yaml.safe_dump(record, sort_keys=False, allow_unicode=True)
        request_path = f"requests/{request.environment.value}/{request.name}.yaml"
        pull_request_url: str | None = None

        gke_tf_path, gke_tf_content = self._render_gke_tf(record)
        if self.github:
            pull_request_url = await self.github.create_request_pull_request(
                request_path=request_path,
                yaml_text=yaml_text,
                cluster_name=request.name,
                actor=actor,
                extra_files={gke_tf_path: gke_tf_content},
            )
            status = "PENDING_REVIEW"
            message = "Request validated and a pull request was opened"
        else:
            self.local_repository.write_record(
                request.environment.value,
                request.name,
                yaml_text,
            )
            (self.settings.root_dir / gke_tf_path).parent.mkdir(parents=True, exist_ok=True)
            (self.settings.root_dir / gke_tf_path).write_text(gke_tf_content, encoding="utf-8")
            status = "LOCAL_CREATED"
            message = "Request validated and written to the local requests directory"

        return RequestSubmission(
            name=request.name,
            status=status,
            message=message,
            request_path=request_path,
            pull_request_url=pull_request_url,
            resolved_network=resolved_network,
        )

    def start_provision(self, name: str) -> ProvisionJob:
        if self.github is not None:
            raise RequestValidationError(
                ["Local provisioning is only available in storage_mode=local"]
            )
        if not self.settings.enable_local_provisioning:
            raise RequestValidationError(
                ["Local provisioning is disabled. Set FACTORY_ENABLE_LOCAL_PROVISIONING=true in .env"]
            )
        request_path = self.local_repository.get_record_path(name)
        if request_path is None:
            raise RequestValidationError([f"No local request named {name} was found"])
        return self.provisioner.start(name, request_path)

    def provision_status(self, name: str) -> dict | None:
        job = self.provisioner.get(name)
        return job.snapshot() if job else None

    async def summaries(self) -> list[RequestSummary]:
        summaries: list[RequestSummary] = []
        for record in await self.records():
            spec = record.get("spec", {})
            metadata = record.get("metadata", {})
            status = record.get("status", {})
            summaries.append(
                RequestSummary(
                    name=metadata.get("name", "unknown"),
                    project_id=spec.get("project_id", "unknown"),
                    environment=spec.get("environment", "unknown"),
                    region=spec.get("region", "unknown"),
                    blueprint=spec.get("blueprint", "unknown"),
                    owner_team=spec.get("owner", {}).get("team", "unknown"),
                    status=status.get("phase", "REQUESTED"),
                    created_at=metadata.get("created_at", ""),
                    pull_request_url=status.get("pull_request_url"),
                    gpu_enabled=bool(spec.get("gpu", {}).get("enabled")),
                )
            )
        return sorted(summaries, key=lambda item: item.created_at, reverse=True)

    def _render_gke_tf(self, record: dict[str, Any]) -> tuple[str, str]:
        try:
            return render_from_document(
                record,
                self.settings.root_dir,
                module_source=self.settings.gke_module_source or DEFAULT_MODULE_SOURCE,
                create_project=self.settings.create_cluster_projects,
                project_parent=self.settings.cluster_project_parent,
                billing_account=self.settings.billing_account,
            )
        except ValueError as exc:
            raise RequestValidationError([f"Could not render gke.tf: {exc}"]) from exc

    def _build_record(
        self,
        request: ClusterRequestCreate,
        validation: ValidationResult,
        resolved_network: ResolvedNetwork,
        actor: str,
    ) -> dict[str, Any]:
        spec = deepcopy(validation.normalized or request.model_dump(mode="json"))
        return {
            "apiVersion": "platform.example.com/v1alpha1",
            "kind": "GKEClusterRequest",
            "metadata": {
                "name": request.name,
                "created_at": utc_now(),
                "created_by": actor,
                "labels": {
                    "environment": request.environment.value,
                    "team": request.owner.team,
                },
            },
            "spec": spec,
            "resolved": {
                "network": resolved_network.model_dump(mode="json"),
            },
            "status": {
                "phase": "REQUESTED",
                "conditions": [
                    {
                        "type": "SchemaValid",
                        "status": "True",
                        "last_transition_time": utc_now(),
                    },
                    {
                        "type": "PolicyValid",
                        "status": "True",
                        "last_transition_time": utc_now(),
                    },
                ],
            },
        }