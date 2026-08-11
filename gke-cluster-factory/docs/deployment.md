# Production deployment guide

This guide assumes an existing Google Cloud organization, billing account, GitHub repository, Cloud Identity groups, and an administrator capable of creating the initial platform resources.

## 1. Prepare identity groups

Create or identify these groups:

| Group | Purpose |
|---|---|
| Portal users | Allowed to open the factory UI through IAP |
| GKE security group | Cloud Identity group-of-groups configured for Google Groups authentication in GKE |
| Platform administrators | Receives cluster administration through GitOps |
| Per-team owner group | Receives project viewer, Connect Gateway, and namespace access |

Replace the two `@example.com` values in `config/profiles.yaml` for local rendering, or provide real values through GitHub variables:

```text
GKE_SECURITY_GROUP
PLATFORM_ADMIN_GROUP
```

Production preflight intentionally rejects example values.

## 2. Prepare bootstrap variables

```bash
cd terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars
```

Edit the file:

```hcl
platform_project_id       = "prj-gke-factory-prod"
create_platform_project   = false
platform_project_parent   = "folders/123456789"
billing_account           = "000000-000000-000000"
cluster_folder_id         = "987654321"
shared_vpc_host_project_id = "prj-network-prod"
region                    = "us-west1"
github_owner              = "your-org"
github_repository         = "gke-cluster-factory"
artifact_repository_name  = "gke-cluster-factory"
```

Set `create_platform_project = true` only when the bootstrap identity is allowed to create the platform project.

## 3. Apply bootstrap

Bootstrap is intentionally run by an administrator. Its state is local unless you add an organization bootstrap backend.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -out bootstrap.tfplan
terraform apply bootstrap.tfplan
```

Capture the outputs:

```bash
terraform output
```

Expected values include:

- Terraform state bucket
- Artifact Registry repository
- GitHub Actions service account
- Workload Identity provider
- GitHub token secret ID

## 4. Add the portal GitHub credential

Use a fine-grained token or GitHub App installation token with the minimum repository permissions needed to read contents, create branches, write files under `requests/`, and create pull requests.

```bash
printf '%s' "$GITHUB_PORTAL_TOKEN" | \
  gcloud secrets versions add gke-factory-github-token \
  --data-file=- \
  --project prj-gke-factory-prod
```

Do not put the token in Terraform state or commit it to Git.

## 5. Configure GitHub variables

Repository or environment variables:

```text
GCP_WORKLOAD_IDENTITY_PROVIDER
GCP_TERRAFORM_SERVICE_ACCOUNT
TF_STATE_BUCKET
PLATFORM_PROJECT_ID
GCP_REGION
ARTIFACT_REPOSITORY
PORTAL_INVOKER_GROUP
GKE_SECURITY_GROUP
PLATFORM_ADMIN_GROUP
CREATE_CLUSTER_PROJECTS
CLUSTER_PROJECT_PARENT
BILLING_ACCOUNT
```

Example values:

```text
GCP_REGION=us-west1
ARTIFACT_REPOSITORY=gke-cluster-factory
PORTAL_INVOKER_GROUP=gke-factory-users@example.org
GKE_SECURITY_GROUP=gke-security-groups@example.org
PLATFORM_ADMIN_GROUP=gke-platform-admins@example.org
CREATE_CLUSTER_PROJECTS=true
CLUSTER_PROJECT_PARENT=folders/987654321
```

When `CREATE_CLUSTER_PROJECTS=false`, each request must name an existing project that the CI identity can administer.

## 6. Configure GitHub secrets

For a private repository, create:

```text
ARGOCD_GIT_USERNAME
ARGOCD_GIT_TOKEN
```

The token should be read-only for Argo CD. For stronger security, replace the username and token secret with a GitHub App or SSH deploy key integration.

## 7. Configure environments and branch protection

Create GitHub environments:

```text
cluster-plan
cluster-production
cluster-destruction
platform-production
```

Recommended controls:

- require designated platform reviewers for `cluster-plan` because it uses cloud and Terraform state read access
- require designated platform reviewers for `cluster-production`
- require platform and data-owner reviewers for `cluster-destruction`
- restrict environment deployment branches to `main`
- require signed commits if supported by your organization
- protect `main`
- require pull requests and CODEOWNERS review
- require branches to be current before merge, which makes concurrent requests rerun the repository-wide collision check
- require `CI` and `Cluster request plan` checks
- disable force pushes and branch deletion
- allow only the reconciliation status workflow, or an organization GitHub App, to bypass the rule for status-only commits under `requests/`

## 8. Deploy the portal

Run the `Deploy self-service portal` workflow or push a change under the paths watched by `.github/workflows/deploy-portal.yml`.

The workflow:

1. authenticates to Google Cloud through Workload Identity Federation
2. builds the container
3. pushes it to Artifact Registry
4. deploys the Cloud Run service through Terraform
5. enables IAP directly on Cloud Run
6. grants IAP access to `PORTAL_INVOKER_GROUP`

For an organization project, the Google-managed OAuth client can normally support in-organization identities. Projects outside an organization can require a one-time IAP OAuth setup through the Google Cloud console.

## 9. Submit a cluster request

Open the portal URL from the deployment output, authenticate through IAP, choose a blueprint, complete the form, and submit.

The portal creates:

```text
requests/<environment>/<cluster-name>.yaml
```

on a new branch, then opens a pull request.

## 10. Review the pull request

The plan workflow performs:

- request model validation
- blueprint policy validation
- identity placeholder rejection
- project and region checks
- H100 quota, machine type, accelerator, and reservation checks when applicable
- Terraform initialization and plan

Review the request, warnings, cloud preflight, cost implications, CIDR allocation, and Terraform plan before merging.

## 11. Reconciliation after merge

The apply workflow:

1. sets request phase to `PROVISIONING`
2. renders a Terraform JSON variable file
3. initializes the per-cluster GCS state prefix
4. applies project, network, GKE, IAM, KMS, Fleet, and backup resources
5. obtains Kubernetes credentials through Fleet Connect Gateway
6. installs Argo CD
7. creates the root application
8. waits for nodes and reports H100 nodes when requested
9. records `READY` in the request file and pushes the audit status

## 12. Access a cluster

Cluster owners and platform administrators can use the Fleet membership output:

```bash
gcloud container fleet memberships get-credentials MEMBERSHIP \
  --project CLUSTER_PROJECT_ID \
  --location us-west1
kubectl auth can-i get pods -n TEAM_NAMESPACE
```

The owner group is granted Google Cloud Connect Gateway roles. Kubernetes RBAC determines what the user can do after reaching the API.

## 13. Shared VPC mode

Set request network mode to `shared` and supply `host_project_id`.

Before approval, confirm:

- the service project can attach to the host project
- subnet ownership is clear
- Cloud NAT is not duplicated
- DNS and hybrid routes are present
- firewall policy permits required control-plane and node communication
- organization policy allows the configuration

The reference module can create a subnet and NAT in the host project. In a centrally governed network, modify the module to consume an existing approved subnet instead.

## 14. H100 production requests

Before merge, verify:

- H100 quota in `us-west1`
- A3 machine type offering in every requested zone
- accelerator offering in every requested zone
- a reservation with the correct zone and shape when reservation mode is selected
- maximum requested GPU count fits quota and budget
- the application tolerates the GPU taint and selects the H100 label
- capacity and startup expectations are accepted by the workload owner

The included preflight validates visible quota and reservation objects, but it cannot guarantee that capacity will be delivered until Google Cloud accepts provisioning.

## 15. First production readiness review

Before approving the first real cluster, perform a controlled test in a non-production folder:

- provision a CPU-only development cluster
- connect through Fleet
- confirm owner and administrator RBAC
- confirm private endpoint behavior
- deploy a rejected Pod to test admission controls
- deploy an allowed sample workload
- verify logs and metrics
- create and restore a backup
- exercise the destruction workflow
- review Terraform state retention and audit logs

Then run a separate H100 proof of capacity with the account team and capacity reservation owner.
