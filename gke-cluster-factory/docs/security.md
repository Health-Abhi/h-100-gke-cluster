# Security model

## Security objectives

The reference implementation aims to provide:

- authenticated self-service access
- reviewed and auditable infrastructure changes
- keyless CI authentication to Google Cloud
- private GKE networking
- least-privilege human and workload access
- policy controls before and after provisioning
- encrypted secrets and backups
- controlled software sources
- deliberate destruction

## Portal security

Production deployment enables Identity-Aware Proxy directly on Cloud Run. The approved portal Google Group receives `roles/iap.httpsResourceAccessor`. The IAP service agent receives Cloud Run Invoker. The FastAPI service reads the authenticated user header and records the actor in the request YAML.

Application security controls include:

- restrictive Content Security Policy
- frame denial
- content-type sniffing protection
- referrer suppression
- disabled browser camera, microphone, and geolocation permissions
- optional bearer token for local or additional API protection
- request validation before persistence
- read-only container filesystem in Docker Compose
- non-root container execution

The GitHub credential is read from Secret Manager by the dedicated portal runtime service account.

## CI identity

GitHub Actions exchanges its OIDC assertion for Google credentials through Workload Identity Federation. The provider condition binds federation to the configured repository. No downloaded service-account key is required.

The bootstrap role set is broad because the CI identity creates projects and cluster infrastructure. Production organizations should replace broad predefined roles with custom roles after observing the actual permission set. Keep project creation and Shared VPC permissions at the narrowest folder and host-project scope possible.

## Human access model

| Principal | Cloud access | Kubernetes access |
|---|---|---|
| Portal users | IAP access to portal | None by default |
| Cluster owner group | Cluster viewer plus Connect Gateway roles | Namespace-scoped owner role |
| Platform admin group | Platform-controlled Google Cloud access | `cluster-admin` through GitOps |
| Break-glass group | Organization-specific temporary elevation | Not created by this reference |

Google Groups authentication requires the configured GKE security group-of-groups and team groups to be managed in Cloud Identity according to Google Groups for GKE requirements.

## Workload identity

Workload Identity Federation for GKE is enabled. Applications should use Kubernetes ServiceAccounts mapped to Google Cloud permissions through principal identifiers or IAM service-account impersonation, depending on the organization's standard.

Do not use static service-account JSON keys in Pods.

## Network security

The cluster uses:

- VPC-native networking
- private nodes
- private control-plane endpoint by default
- Master Authorized Networks when a public endpoint is explicitly enabled
- Private Google Access
- optional Cloud NAT
- Dataplane V2
- disabled Kubernetes Service external IPs
- default-deny namespace network policies

The baseline permits DNS, the metadata server, and Google API VIP egress required for normal platform operation. Review those rules against your application dependencies and VPC Service Controls design.

NetworkPolicy is not a replacement for VPC firewall policy, service perimeter controls, DNS policy, or application authorization.

## Node security

Node pools use:

- dedicated node service account
- only the project roles needed for image pulling, logging, and monitoring
- Container-Optimized OS with containerd
- Shielded VM Secure Boot and integrity monitoring
- legacy metadata endpoint disabled
- GKE metadata mode
- auto-repair and auto-upgrade
- gVNIC
- separate system, general, and GPU pools

The H100 pool is isolated with labels and a `NoSchedule` taint.

## Encryption

Kubernetes secrets use a customer-managed Cloud KMS key. The GKE service agent is granted encrypt and decrypt access. Backup for GKE uses the same key and its service identity receives the required key permission.

The state bucket uses Google Cloud encryption by default and has uniform access, public access prevention, versioning, a retention period, and archived-version cleanup. Organizations requiring CMEK for state should extend the bootstrap module.

## Admission policy

The baseline uses Kubernetes ValidatingAdmissionPolicy resources to enforce controls without adding another policy-controller dependency.

Controls include:

- no host network, host PID, or host IPC
- no hostPath volumes
- non-root execution
- RuntimeDefault seccomp
- no privilege escalation
- all Linux capabilities dropped
- CPU and memory requests and limits
- required ownership labels
- image digest pinning
- approved image registry prefixes
- production minimum replicas
- zone topology spread
- workload exposure restrictions for LoadBalancer Services

Policies select managed application namespaces through labels so platform namespaces can be bootstrapped safely. Extend selectors carefully and test failure policy before broad enforcement.

## Image supply chain

GKE Binary Authorization evaluation is enabled. The reference also applies admission checks for digest pinning and approved registries.

The repository does not create a signing authority, attestor, CI signing step, or organization-specific Binary Authorization policy. A signed-image guarantee requires those elements. See [binary-authorization.md](binary-authorization.md).

## Secrets

The chart does not install a generic external-secrets controller. Applications should use an approved organization pattern, such as the Secret Manager CSI driver or Workload Identity-based retrieval, and should keep secret values out of Git.

The `include_secrets` backup option is useful for recovery but increases the sensitivity of backup data. Retention, access, and key policy should reflect the workload classification.

## Audit evidence

Audit evidence is distributed across:

- IAP and Cloud Run request logs
- Git history and pull-request approvals
- GitHub Actions workflow logs
- Workload Identity Federation audit logs
- Terraform state and plan output
- Google Cloud Admin Activity and Data Access logs
- GKE audit logs
- Argo CD application history
- request status conditions committed to Git
- Backup for GKE plan and restore records

Route required logs to a central project and SIEM according to retention and compliance policy.

## Organization controls to add

Common landing-zone additions include:

- domain-restricted sharing
- disable service-account key creation
- require Shielded VMs
- restrict external IP addresses
- restrict allowed regions
- require uniform bucket-level access
- require CMEK for selected services
- VPC Service Controls
- centralized hierarchical firewall policies
- approved Artifact Registry locations
- Security Command Center Premium controls
- budget and anomaly alerts

These controls should normally be managed above the cluster factory so they apply consistently to every project.
