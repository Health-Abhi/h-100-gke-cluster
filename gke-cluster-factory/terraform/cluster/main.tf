locals {
  network_project_id = coalesce(var.network.host_project_id, var.project_id)
  project_parent_id  = var.project_parent == null ? null : split("/", var.project_parent)[1]
  common_labels = merge(var.labels, {
    cluster     = var.cluster_name
    environment = var.environment
    blueprint   = var.blueprint
  })
  required_apis = toset([
    "artifactregistry.googleapis.com",
    "binaryauthorization.googleapis.com",
    "cloudkms.googleapis.com",
    "compute.googleapis.com",
    "connectgateway.googleapis.com",
    "container.googleapis.com",
    "gkebackup.googleapis.com",
    "gkehub.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
  ])
}

resource "google_project" "cluster" {
  count = var.create_project ? 1 : 0

  project_id      = var.project_id
  name            = var.cluster_name
  billing_account = var.billing_account
  folder_id       = var.project_parent != null && startswith(var.project_parent, "folders/") ? local.project_parent_id : null
  org_id          = var.project_parent != null && startswith(var.project_parent, "organizations/") ? local.project_parent_id : null
  labels          = local.common_labels

  lifecycle {
    precondition {
      condition     = var.billing_account != null && var.project_parent != null
      error_message = "create_project requires billing_account and project_parent."
    }
  }
}

resource "google_project_service" "apis" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false

  depends_on = [google_project.cluster]
}

resource "google_project_service" "network_compute" {
  count = local.network_project_id == var.project_id ? 0 : 1

  provider           = google.network
  project            = local.network_project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

module "network" {
  source = "../modules/network"

  providers = {
    google = google.network
  }

  service_project_id = var.project_id
  network_project_id = local.network_project_id
  region             = var.region
  mode               = var.network.mode
  network_name       = var.network.network_name
  subnet_name        = var.network.subnet_name
  node_cidr          = var.network.node_cidr
  pod_cidr           = var.network.pod_cidr
  service_cidr       = var.network.service_cidr
  pod_range_name     = var.network.pod_range_name
  service_range_name = var.network.service_range_name
  create_nat         = var.network.create_nat

  depends_on = [
    google_project_service.apis,
    google_project_service.network_compute,
  ]
}

module "gke" {
  source = "../modules/gke"

  project_id            = var.project_id
  cluster_name          = var.cluster_name
  region                = var.region
  node_locations        = var.node_locations
  network_self_link     = module.network.network_self_link
  subnetwork_self_link  = module.network.subnetwork_self_link
  pod_range_name        = var.network.pod_range_name
  service_range_name    = var.network.service_range_name
  control_plane_cidr    = var.network.control_plane_cidr
  private_endpoint_only = var.network.private_endpoint_only
  authorized_cidrs      = var.network.authorized_cidrs
  release_channel       = var.release_channel
  deletion_protection   = var.deletion_protection
  owner_group           = var.owner_group
  platform_admin_group  = var.platform_admin_group
  gke_security_group    = var.gke_security_group
  iam_principal_type        = var.iam_principal_type
  enable_google_groups_rbac = var.enable_google_groups_rbac
  labels                = local.common_labels
  max_pods_per_node     = var.capacity.max_pods_per_node
  system_machine_type   = var.system_machine_type
  general_machine_type  = var.general_machine_type
  system_min_nodes      = var.capacity.system_min_nodes
  system_max_nodes      = var.capacity.system_max_nodes
  general_min_nodes     = var.capacity.general_min_nodes
  general_max_nodes     = var.capacity.general_max_nodes
  gpu                   = var.gpu

  depends_on = [
    google_project_service.apis,
    module.network,
  ]
}

module "backup" {
  source = "../modules/backup"
  count  = var.backup.tier == "none" ? 0 : 1

  project_id          = var.project_id
  cluster_id          = module.gke.cluster_id
  cluster_name        = var.cluster_name
  region              = var.region
  labels              = local.common_labels
  retention_days      = var.backup.retention_days
  delete_lock_days    = var.backup.delete_lock_days
  target_rpo_minutes  = var.backup.target_rpo_minutes
  include_volume_data = var.backup.include_volume_data
  include_secrets     = var.backup.include_secrets
  kms_key_id          = module.gke.kms_key_id
  deletion_protection = var.deletion_protection

  depends_on = [module.gke]
}
