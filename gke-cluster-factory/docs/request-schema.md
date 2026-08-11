# Cluster request schema

The API accepts a `ClusterRequestCreate` JSON document. The persisted form is a `GKEClusterRequest` YAML record with platform metadata, resolved IP ranges, and lifecycle status.

## Minimal CPU production request

```yaml
name: payments-prod-usw1
project_id: prj-payments-prod
blueprint: standard-prod-v1
environment: prod
region: us-west1
owner:
  team: payments
  google_group: gcp-payments@example.org
  cost_center: cc-1042
workload:
  data_classification: confidential
  exposure: internal
capacity:
  system_min_nodes: 3
  system_max_nodes: 9
  general_min_nodes: 3
  general_max_nodes: 30
  max_pods_per_node: 64
availability:
  tier: regional-ha
  application_minimum_replicas: 3
backup:
  tier: gold
  retention_days: 90
  delete_lock_days: 7
  target_rpo_minutes: 60
  include_volume_data: true
  include_secrets: true
network:
  mode: dedicated
  network_name: gke-platform
  create_nat: true
  private_endpoint_only: true
  authorized_cidrs: []
lifecycle:
  deletion_protection: true
labels:
  application: payments
```

## Top-level fields

| Field | Type | Rules |
|---|---|---|
| `name` | string | Lowercase DNS label, 3 to 40 characters |
| `project_id` | string | Valid Google Cloud project ID, 6 to 30 characters |
| `blueprint` | string | Must exist in `config/profiles.yaml` |
| `environment` | enum | `dev`, `test`, `stage`, or `prod` |
| `region` | string | Must be in catalog `allowed_regions` |
| `owner` | object | Required ownership and billing metadata |
| `workload` | object | Classification, exposure, and description |
| `capacity` | object | System and general autoscaling boundaries |
| `gpu` | object | Optional accelerator pool configuration |
| `availability` | object | Application availability intent |
| `backup` | object | Backup tier and retention intent |
| `network` | object | Dedicated or Shared VPC intent |
| `lifecycle` | object | Deletion and expiration settings |
| `labels` | map | Additional lowercase Google Cloud labels |

## Owner

| Field | Required | Description |
|---|---:|---|
| `team` | Yes | Normalized team identifier |
| `google_group` | Yes | Group used for owner access |
| `cost_center` | Yes | Billing and reporting tag |
| `technical_contact` | No | Operational contact, defaults to owner group |

## Workload

`data_classification` values:

```text
public
internal
confidential
restricted
```

`exposure` values:

```text
none
internal
external
```

Restricted workloads cannot request external exposure and require a private-only control-plane endpoint.

## Capacity

| Field | Range |
|---|---:|
| `system_min_nodes` | 1 to 30 |
| `system_max_nodes` | 1 to 60 |
| `general_min_nodes` | 0 to 100 |
| `general_max_nodes` | 1 to 1000 |
| `max_pods_per_node` | 8 to 256 |

Each maximum must be greater than or equal to its minimum. Production policy requires at least three system nodes and three general nodes.

The values are total node counts across the regional node pool, not per-zone application replicas.

## GPU

| Field | Description |
|---|---|
| `enabled` | Creates the dedicated GPU pool |
| `model` | Approved accelerator type, currently `nvidia-h100-80gb` |
| `machine_type` | Approved A3 machine type |
| `accelerator_count` | GPUs per node |
| `minimum_nodes` | Total lower autoscaling boundary |
| `maximum_nodes` | Total upper autoscaling boundary |
| `zones` | Up to three zones in the selected region |
| `provisioning_model` | `standard`, `spot`, `flex-start`, or `reservation` |
| `reservation_name` | Required for reservation mode |

Production H100 policy rejects Spot and Flex-start, requires at least one minimum node, and recommends reservation-backed capacity.

## Availability

`application_minimum_replicas` is an application policy input. Production requires at least three. The GitOps baseline independently rejects production Deployments and StatefulSets with fewer than three replicas in selected namespaces.

`secondary_region` is reserved for a future multi-region blueprint. The current implementation does not create a second cluster.

## Backup

Tiers:

```text
none
bronze
silver
gold
```

Production cannot select `none`. Delete-lock days cannot exceed retention days. Target RPO is between 60 and 86,400 minutes.

The catalog supplies defaults, while the request records the accepted values explicitly.

## Network

`mode` is `dedicated` or `shared`.

Shared VPC requires `host_project_id`. A public control-plane endpoint requires one or more strict IPv4 CIDRs in `authorized_cidrs`. IPv6 values and host addresses that are not network boundaries are rejected.

IP ranges are not accepted from the requester. The platform writes these under:

```yaml
resolved:
  network:
    node_cidr: 10.64.0.0/24
    pod_cidr: 10.128.0.0/16
    service_cidr: 172.20.0.0/20
    control_plane_cidr: 172.24.0.0/28
    subnet_name: snet-payments-prod-usw1
    pod_range_name: pods-payments-prod-usw1
    service_range_name: svc-payments-prod-usw1
```

## Lifecycle

Production requires `deletion_protection: true`. Destruction uses a separate approved workflow that first applies `false` and then destroys the state.

Use `expiration_date` for non-production lifecycle automation. The current reference records the date and warns when it is missing, but it does not include a scheduled janitor. Add a scheduled workflow that opens cleanup requests based on this field.

## Labels

Keys must start with a lowercase letter and can contain lowercase letters, numbers, underscore, and hyphen. Values use lowercase letters, numbers, underscore, and hyphen.

The service adds:

```text
environment
team
cost-center
managed-by=gke-cluster-factory
```

## Persisted status

Example:

```yaml
status:
  phase: READY
  conditions:
    - type: Reconciled
      status: "True"
      message: Infrastructure and GitOps baseline reconciled
      last_transition_time: "2026-07-20T00:00:00Z"
```

Status is an audit convenience. Terraform state and cloud resource state remain the authoritative infrastructure records.
