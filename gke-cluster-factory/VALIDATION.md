# Validation record

This record describes what was executed against the packaged reference implementation on July 20, 2026.

## Checks completed successfully

- Ruff static analysis for `app/`, `tests/`, and `scripts/`
- Sixteen Python unit and API tests
- Request validation, repository-wide collision checks, and Terraform variable rendering tests
- YAML parsing across GitHub Actions, Cloud Build, configuration, GitOps, and sample requests
- Bash syntax checks for every shell script
- JavaScript syntax validation for the portal client
- HCL parsing for all Terraform files
- Live FastAPI smoke test covering health, readiness, catalog, UI, validation, submission, and request listing
- UTF-8 text scan confirming that the repository contains no em dash characters

## Checks represented in CI but not executed locally

The build environment used to prepare this package did not include the Terraform, Helm, kubectl, gcloud, or Docker CLIs. Consequently, these checks are configured in CI but were not executed locally:

- Terraform provider initialization and provider-schema validation
- Terraform plan against a real Google Cloud organization
- Helm lint and rendered-manifest validation with the Helm CLI
- Container image build
- Argo CD installation and synchronization
- GKE Fleet Connect Gateway access
- Google Cloud quota, A3 machine type, H100 accelerator, and reservation preflight
- Live Google Cloud apply and destroy

## Required customer validation

Before approving production use, execute the plan workflow in the target Google Cloud organization and verify:

1. Billing, folder, project creation, and Shared VPC permissions
2. Organization Policy and VPC Service Controls compatibility
3. Real Cloud Identity groups for portal, platform, and team access
4. GCS Terraform state access and locking behavior
5. Cloud Run IAP access from intended identities
6. GKE version, regional capacity, quotas, and maintenance policy
7. A3 and H100 availability plus reservation fit for GPU profiles
8. Backup creation and an actual restore exercise
9. Admission-policy behavior with representative workloads
10. Controlled cluster destruction and recovery from a failed reconciliation

A passing local suite proves the repository logic and packaging are internally coherent. It does not substitute for a Terraform plan, security review, or controlled deployment in the destination organization.
