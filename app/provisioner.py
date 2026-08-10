"""Portal-triggered local provisioning.

This module lets the "Provision" button in the portal run the same
Terraform reconciliation that `.github/workflows/request-apply.yml` runs in
CI, but directly on the machine hosting the portal. It is a convenience for
local/demo use — production deployments should still go through the
GitHub Actions pipeline with PR review and Workload Identity Federation.

Design notes:
- Cross-platform (Windows/macOS/Linux): everything below is invoked as
  `sys.executable script.py ...` or a plain binary (`terraform`, `gcloud`)
  rather than the repository's bash (.sh) helper scripts, since bash is not
  guaranteed to be present on Windows.
- Jobs run in a background thread per request name. Output is captured
  line-by-line into an in-memory log the UI polls.
- This does *not* run scripts/preflight_gcp.sh or scripts/bootstrap_cluster.sh
  (both bash). Preflight-equivalent project/region checks are re-implemented
  in Python below. GitOps bootstrap (Argo CD) is left as a manual follow-up
  step and noted in the final log line.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml

from app.config import Settings

JobStatus = Literal["running", "succeeded", "failed"]


@dataclass
class ProvisionJob:
    name: str
    status: JobStatus = "running"
    logs: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, line: str) -> None:
        with self._lock:
            self.logs.append(line)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "status": self.status,
                "logs": list(self.logs),
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


class ProvisionManager:
    """Tracks one background provisioning job per request name."""

    def __init__(self, settings: Settings, root_dir: Path):
        self.settings = settings
        self.root_dir = root_dir
        self._jobs: dict[str, ProvisionJob] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> ProvisionJob | None:
        with self._lock:
            return self._jobs.get(name)

    def start(self, name: str, request_path: Path) -> ProvisionJob:
        with self._lock:
            existing = self._jobs.get(name)
            if existing is not None and existing.status == "running":
                raise RuntimeError(f"Provisioning is already running for {name}")
            job = ProvisionJob(name=name)
            self._jobs[name] = job
        thread = threading.Thread(
            target=self._run,
            args=(job, request_path),
            daemon=True,
        )
        thread.start()
        return job

    # -- internal ---------------------------------------------------------

    def _run(self, job: ProvisionJob, request_path: Path) -> None:
        try:
            _run_pipeline(job, request_path, self.root_dir, self.settings)
            job.status = "succeeded"
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            job.log(f"ERROR: {exc}")
            job.status = "failed"
            _set_status_best_effort(
                request_path,
                self.root_dir,
                self.settings,
                phase="FAILED",
                message=f"Local provisioning failed: {exc}",
                condition_status="False",
            )
        finally:
            job.finished_at = datetime.now(UTC).isoformat()


def _run_pipeline(job: ProvisionJob, request_path: Path, root_dir: Path, settings: Settings) -> None:
    record = yaml.safe_load(request_path.read_text(encoding="utf-8"))
    spec = record["spec"]
    cluster_name = record["metadata"]["name"]
    project_id = spec["project_id"]
    region = spec["region"]

    for binary, label in ((settings.terraform_binary, "Terraform"), (settings.gcloud_binary, "gcloud")):
        if shutil.which(binary) is None:
            raise RuntimeError(
                f"{label} binary '{binary}' was not found on PATH. Install it and/or set "
                f"FACTORY_TERRAFORM_BINARY / FACTORY_GCLOUD_BINARY in .env to the full path."
            )

    if not settings.gke_security_group or not settings.platform_admin_group:
        raise RuntimeError(
            "Set FACTORY_GKE_SECURITY_GROUP and FACTORY_PLATFORM_ADMIN_GROUP in .env "
            "(use your own email if this is a personal, non-Workspace GCP account, and also "
            "set FACTORY_IAM_PRINCIPAL_TYPE=user and FACTORY_ENABLE_GOOGLE_GROUPS_RBAC=false)."
        )

    if not settings.tf_state_bucket:
        raise RuntimeError(
            "Set FACTORY_TF_STATE_BUCKET in .env to a GCS bucket for Terraform state "
            "(e.g. create one with: gcloud storage buckets create gs://YOUR-BUCKET "
            f"--project {project_id})."
        )

    job.log(f"Starting local provisioning for '{cluster_name}' in project '{project_id}' ({region})")
    _set_status_best_effort(
        request_path, root_dir, settings,
        phase="PROVISIONING", message="Local provisioning started", condition_status="Unknown",
    )

    validate_cmd = [sys.executable, str(root_dir / "scripts" / "validate_request.py"), str(request_path)]
    _run_step(job, validate_cmd, root_dir)

    if settings.skip_preflight:
        job.log("Skipping preflight (FACTORY_SKIP_PREFLIGHT=true)")
    else:
        _python_preflight(job, spec, settings)

    tfvars_fd, tfvars_path = tempfile.mkstemp(suffix=".tfvars.json")
    os.close(tfvars_fd)
    try:
        _run_step(
            job,
            [
                sys.executable,
                str(root_dir / "scripts" / "render_tfvars.py"),
                str(request_path),
                "--output",
                tfvars_path,
            ],
            root_dir,
        )

        cluster_dir = root_dir / "terraform" / "cluster"
        init_cmd = [
            settings.terraform_binary,
            f"-chdir={cluster_dir}",
            "init",
            "-reconfigure",
            f"-backend-config=bucket={settings.tf_state_bucket}",
            f"-backend-config=prefix=gke-clusters/{cluster_name}",
        ]
        _run_step(job, init_cmd, root_dir)

        apply_cmd = [
            settings.terraform_binary,
            f"-chdir={cluster_dir}",
            "apply",
            "-input=false",
            "-auto-approve",
            "-lock-timeout=10m",
            f"-var-file={tfvars_path}",
        ]
        if settings.create_cluster_projects:
            apply_cmd += [
                "-var=create_project=true",
                f"-var=project_parent={settings.cluster_project_parent}",
                f"-var=billing_account={settings.billing_account}",
            ]
        _run_step(job, apply_cmd, root_dir)
    finally:
        Path(tfvars_path).unlink(missing_ok=True)

    job.log("Terraform apply completed. The GKE cluster has been created.")

    gke_tf_cmd = [
        sys.executable,
        str(root_dir / "scripts" / "render_gke_tf.py"),
        str(request_path),
        "--repository-root",
        str(root_dir),
    ]
    if settings.gke_module_source:
        gke_tf_cmd += ["--module-source", settings.gke_module_source]
    if settings.create_cluster_projects:
        gke_tf_cmd += [
            "--create-project",
            "--project-parent",
            settings.cluster_project_parent or "",
            "--billing-account",
            settings.billing_account or "",
        ]
    _run_step(job, gke_tf_cmd, root_dir)
    job.log(
        f"Wrote clusters/{project_id}_{cluster_name}/gke.tf (project, folder/org, billing account, "
        "and cluster settings pulled from this request)."
    )
    job.log(
        "Next (manual, optional): connect via Fleet Connect Gateway and run "
        "scripts/bootstrap_cluster.sh (requires bash / Git Bash) to install Argo CD "
        "and the platform baseline."
    )
    _set_status_best_effort(
        request_path, root_dir, settings,
        phase="READY", message="Infrastructure reconciled by local provisioning", condition_status="True",
    )


def _python_preflight(job: ProvisionJob, spec: dict, settings: Settings) -> None:
    """Minimal, cross-platform re-implementation of scripts/preflight_gcp.sh."""
    project_id = spec["project_id"]
    region = spec["region"]

    job.log(f"Preflight: checking project '{project_id}' is accessible")
    result = subprocess.run(
        [settings.gcloud_binary, "projects", "describe", project_id, "--format=value(projectId)"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if settings.create_cluster_projects:
            job.log(
                f"Project {project_id} not found yet; Terraform will create it "
                "(create_cluster_projects=true)"
            )
        else:
            raise RuntimeError(
                f"Project {project_id} does not exist or is not visible to the "
                f"current gcloud identity: {result.stderr.strip()}"
            )
    else:
        job.log(f"OK: project {project_id} is accessible")

        job.log(f"Preflight: checking region '{region}'")
        result = subprocess.run(
            [settings.gcloud_binary, "compute", "regions", "describe", region,
             f"--project={project_id}", "--format=value(name)"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Region {region} is not available to project {project_id}: {result.stderr.strip()}"
            )
        job.log(f"OK: region {region} is available")

    gpu = spec.get("gpu", {})
    if gpu.get("enabled"):
        job.log(
            "GPU is enabled on this request. This local preflight does not check H100 "
            "quota/reservations (that logic lives in scripts/preflight_gcp.sh, bash-only). "
            "Verify quota manually before applying if you're on a fresh project."
        )


def _run_step(job: ProvisionJob, cmd: list[str], cwd: Path) -> None:
    job.log(f"$ {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        job.log(line.rstrip("\n"))
    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(f"Command failed with exit code {returncode}: {' '.join(cmd)}")


def _set_status_best_effort(
    request_path: Path,
    root_dir: Path,
    settings: Settings,
    *,
    phase: str,
    message: str,
    condition_status: str,
) -> None:
    import contextlib

    with contextlib.suppress(OSError):
        subprocess.run(
            [
                sys.executable,
                str(root_dir / "scripts" / "set_request_status.py"),
                str(request_path),
                phase,
                "--condition", "Reconciled",
                "--status", condition_status,
                "--message", message,
            ],
            cwd=root_dir,
            capture_output=True, text=True, check=False,
        )
