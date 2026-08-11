# Operations runbook

## Request lifecycle

| Phase | Meaning |
|---|---|
| `REQUESTED` | Schema and platform policy passed |
| `PENDING_REVIEW` | Portal opened a pull request |
| `PROVISIONING` | Terraform apply started |
| `READY` | Infrastructure and baseline reconciliation completed |
| `FAILED` | Plan, apply, GitOps, or destroy reconciliation requires operator attention |
| `DELETING` | Approved destruction started |
| `DESTROYED` | Terraform destroy completed |

A failed reconciliation records `FAILED` when the workflow reaches the status handler. Failures before checkout or status initialization can leave the previous phase in Git. Use the workflow logs, Terraform state, and Google Cloud operations as the primary diagnostic sources before editing status manually.

## Daily checks

- failed plan or reconcile workflows
- clusters with unhealthy nodes
- pending GKE upgrades
- admission policy denials above normal baseline
- IPAM pool consumption
- Terraform state lock failures
- Cloud NAT exhaustion and egress errors
- Pod and Service secondary range utilization
- Backup for GKE schedule failures
- H100 node pool provisioning failures
- stale pull requests and expired non-production clusters

## Request troubleshooting

### Portal says request is blocked

1. Read the API validation detail shown in the UI.
2. Confirm the blueprint allows the selected environment.
3. Confirm production node minima, replicas, backup, and deletion protection.
4. Confirm H100 fields match the blueprint.
5. Confirm a public control-plane endpoint includes authorized CIDRs.
6. Confirm Shared VPC has a host project ID.

### Portal cannot create a pull request

1. Verify Cloud Run can access the Secret Manager token.
2. Verify token repository permissions.
3. Verify the configured owner, repository, and default branch.
4. Check Cloud Run logs for GitHub API response details.
5. Rotate the token if it is expired or revoked.

### IPAM reports exhaustion

1. Inspect `config/ipam.yaml`.
2. Inventory active and retired request allocations.
3. Do not reuse a range while the original network still exists.
4. Add a new non-overlapping pool through review.
5. For large scale, migrate allocation to a transactional IPAM backend.

## Terraform troubleshooting

### Backend initialization fails

- verify `TF_STATE_BUCKET`
- verify the federated service account has object access
- verify the bucket retention policy does not block required updates
- verify the backend prefix matches the cluster name
- inspect stale state locks before forcing unlock

Never force-unlock without confirming that no other apply is active.

### Project creation fails

- verify folder and billing account values
- verify project ID availability
- verify project creation quota
- verify the CI identity has folder project creator and billing user permissions
- verify organization policies do not block service enablement

### Cluster apply fails

Run:

```bash
gcloud container operations list \
  --project PROJECT_ID \
  --location us-west1
```

Then inspect the operation and Terraform error. Common causes include missing quotas, API service-agent propagation, Shared VPC permission, KMS permission, subnet conflicts, and unavailable node capacity.

## H100 troubleshooting

### Quota preflight fails

Request the required regional H100 quota and associated resource quotas. The preflight calculates the maximum accelerator count from `accelerator_count * maximum_nodes`.

### Reservation check fails

A reservation must exist in each zone listed in the request because the reference preflight checks every requested zone using the same reservation name. Adapt the schema if your organization uses distinct reservation names per zone.

### Nodes remain pending

- inspect GKE and Compute Engine operations
- verify reservation consumption properties
- verify machine type and accelerator zone offering
- verify quota usage has not changed after approval
- inspect maintenance or stockout messages
- reduce or redistribute requested zones only through a reviewed request change

### GPU workload does not schedule

Confirm the Pod has:

```yaml
nodeSelector:
  accelerator: nvidia-h100-80gb

tolerations:
  - key: nvidia.com/gpu
    operator: Equal
    value: present
    effect: NoSchedule

resources:
  limits:
    nvidia.com/gpu: 8
```

Also confirm node allocatable resources and GPU driver status.

## GitOps troubleshooting

### Connect Gateway credentials fail

- confirm Fleet membership is active
- confirm the user or CI identity has required gateway roles
- confirm the `connectgateway.googleapis.com` API is enabled
- include both project and membership location in the command

### Argo CD install fails

- verify Fleet credentials still work
- check network egress to the Argo CD manifest source
- pin and mirror the Argo CD installation manifest into an approved Artifact Registry or Git repository for restricted environments
- verify the `argocd` namespace has sufficient resources

### Baseline application is degraded

```bash
kubectl -n argocd get application platform-baseline -o yaml
kubectl -n argocd get pods
kubectl get validatingadmissionpolicies
kubectl get networkpolicies -A
```

Fix the source or chart and allow Argo CD to reconcile. Avoid one-off production edits that will be reverted by GitOps.

## Backup and restore

### Backup verification

At least daily:

```bash
gcloud beta container backup-restore backups list \
  --project PROJECT_ID \
  --location us-west1 \
  --backup-plan BACKUP_PLAN
```

Verify recent successful backups and alert on RPO violations.

### Restore drill

Run restore drills in an isolated project or cluster:

1. choose a representative backup
2. define namespace and conflict-handling scope
3. restore into a test target
4. validate Kubernetes resources
5. validate persistent data consistency
6. run application smoke tests
7. record actual recovery time and recovery point
8. remove test data according to policy

A backup plan should not be considered production-ready until a restore has been demonstrated.

## Upgrade operations

The cluster uses a release channel, node auto-upgrade, and a weekly maintenance window. Platform owners should still:

- review GKE release notes
- test new versions with a development blueprint
- monitor deprecated Kubernetes APIs
- maintain PodDisruptionBudgets and topology spread
- validate GPU driver and workload compatibility
- pause risky application changes during major platform upgrades

## Capacity and cost

Track:

- system and general node autoscaling boundaries
- H100 minimum nodes and reservation utilization
- persistent disk growth
- logging ingestion
- backup storage and retention
- NAT traffic
- unused non-production clusters

Use expiration dates and an automated policy to open cleanup pull requests for non-production clusters.

## Destruction

Destruction is manual and protected.

1. Open the `Destroy cluster` workflow.
2. Provide the exact request path.
3. Enter `DESTROY <cluster-name>` exactly.
4. Approve the `cluster-destruction` environment.
5. Acknowledge project deletion when the factory created the project.
6. Review final backups and data-owner approval before execution.

The workflow first applies `deletion_protection=false`, then runs Terraform destroy, then records `DESTROYED` in Git.

KMS keys use a destruction schedule. State, backups, project deletion, and legal retention requirements must be reviewed independently.

## Break glass

This repository does not create a break-glass principal. Create an organization-owned emergency group with:

- phishing-resistant authentication
- time-limited membership
- mandatory ticket reference
- alerting on activation and use
- session and command auditing
- periodic access tests

Break-glass changes must be reconciled back into Git or removed immediately after the incident.
