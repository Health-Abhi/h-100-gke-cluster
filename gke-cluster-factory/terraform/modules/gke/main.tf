data "google_project" "current" {
  project_id = var.project_id
}

locals {
  gke_service_agent = "service-${data.google_project.current.number}@container-engine-robot.iam.gserviceaccount.com"
  node_roles = toset([
    "roles/artifactregistry.reader",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/stackdriver.resourceMetadata.writer",
  ])
  monitoring_components = concat(
    ["SYSTEM_COMPONENTS", "APISERVER", "SCHEDULER", "CONTROLLER_MANAGER", "STORAGE", "HPA", "POD", "DAEMONSET", "DEPLOYMENT", "STATEFULSET", "KUBELET", "CADVISOR"],
    var.gpu.enabled ? ["DCGM"] : [],
  )
}

resource "google_service_account" "nodes" {
  project      = var.project_id
  account_id   = trim(substr("gke-${var.cluster_name}-nodes", 0, 30), "-")
  display_name = "GKE nodes for ${var.cluster_name}"
  description  = "Least-privilege node identity managed by GKE Cluster Factory"
}

resource "google_project_iam_member" "node_roles" {
  for_each = local.node_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

resource "google_project_iam_member" "owner_cluster_viewer" {
  project = var.project_id
  role    = "roles/container.clusterViewer"
  member  = "${var.iam_principal_type}:${var.owner_group}"
}

resource "google_project_iam_member" "owner_gateway_reader" {
  project = var.project_id
  role    = "roles/gkehub.gatewayReader"
  member  = "${var.iam_principal_type}:${var.owner_group}"
}

resource "google_project_iam_member" "owner_gateway_admin" {
  project = var.project_id
  role    = "roles/gkehub.gatewayAdmin"
  member  = "${var.iam_principal_type}:${var.owner_group}"
}

resource "google_project_iam_member" "platform_admin_cluster_viewer" {
  project = var.project_id
  role    = "roles/container.clusterViewer"
  member  = "${var.iam_principal_type}:${var.platform_admin_group}"
}

resource "google_project_iam_member" "platform_admin_gateway_reader" {
  project = var.project_id
  role    = "roles/gkehub.gatewayReader"
  member  = "${var.iam_principal_type}:${var.platform_admin_group}"
}

resource "google_project_iam_member" "platform_admin_gateway_admin" {
  project = var.project_id
  role    = "roles/gkehub.gatewayAdmin"
  member  = "${var.iam_principal_type}:${var.platform_admin_group}"
}

resource "google_project_service_identity" "gke_backup" {
  provider = google-beta
  project  = var.project_id
  service  = "gkebackup.googleapis.com"
}

resource "google_kms_key_ring" "gke" {
  project  = var.project_id
  name     = substr("${var.cluster_name}-gke", 0, 63)
  location = var.region
}

resource "google_kms_crypto_key" "gke" {
  name                       = substr("${var.cluster_name}-secrets", 0, 63)
  key_ring                   = google_kms_key_ring.gke.id
  rotation_period            = "7776000s"
  destroy_scheduled_duration = "2592000s"

}

resource "google_kms_crypto_key_iam_member" "gke_service_agent" {
  crypto_key_id = google_kms_crypto_key.gke.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${local.gke_service_agent}"
}

resource "time_sleep" "gke_backup_service_agent_propagation" {
  create_duration = "30s"
  depends_on      = [google_project_service_identity.gke_backup]
}

resource "google_kms_crypto_key_iam_member" "gke_backup_service_agent" {
  crypto_key_id = google_kms_crypto_key.gke.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_project_service_identity.gke_backup.email}"
  depends_on    = [time_sleep.gke_backup_service_agent_propagation]
}

resource "google_container_cluster" "this" {
  provider = google-beta

  project     = var.project_id
  name        = var.cluster_name
  description = "Policy-managed regional GKE cluster created by GKE Cluster Factory"
  location    = var.region

  node_locations          = var.node_locations
  network                 = var.network_self_link
  subnetwork              = var.subnetwork_self_link
  networking_mode         = "VPC_NATIVE"
  datapath_provider       = "ADVANCED_DATAPATH"
  default_max_pods_per_node = var.max_pods_per_node

  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = var.deletion_protection

  enable_legacy_abac          = false
  enable_shielded_nodes       = true
  enable_intranode_visibility = true
  enable_l4_ilb_subsetting    = true

  resource_labels = var.labels

  release_channel {
    channel = var.release_channel
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  dynamic "authenticator_groups_config" {
    for_each = var.enable_google_groups_rbac ? [1] : []
    content {
      security_group = var.gke_security_group
    }
  }

  cost_management_config {
    enabled = true
  }

  vertical_pod_autoscaling {
    enabled = true
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = var.private_endpoint_only
    master_ipv4_cidr_block  = var.control_plane_cidr

    master_global_access_config {
      enabled = false
    }
  }

  dynamic "master_authorized_networks_config" {
    for_each = [1]
    content {
      gcp_public_cidrs_access_enabled = false
      dynamic "cidr_blocks" {
        for_each = { for index, cidr in var.authorized_cidrs : tostring(index) => cidr }
        content {
          cidr_block   = cidr_blocks.value
          display_name = "approved-${cidr_blocks.key}"
        }
      }
    }
  }

  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pod_range_name
    services_secondary_range_name = var.service_range_name
    stack_type                    = "IPV4"
  }

  addons_config {
    horizontal_pod_autoscaling {
      disabled = false
    }

    http_load_balancing {
      disabled = false
    }

    dns_cache_config {
      enabled = true
    }

    gce_persistent_disk_csi_driver_config {
      enabled = true
    }

    gcp_filestore_csi_driver_config {
      enabled = true
    }

    gcs_fuse_csi_driver_config {
      enabled = true
    }

    gke_backup_agent_config {
      enabled = true
    }
  }

  secret_manager_config {
    enabled = true

    rotation_config {
      enabled           = true
      rotation_interval = "120s"
    }
  }

  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }

  database_encryption {
    state    = "ENCRYPTED"
    key_name = google_kms_crypto_key.gke.id
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS", "APISERVER", "CONTROLLER_MANAGER", "SCHEDULER"]
  }

  monitoring_config {
    enable_components = local.monitoring_components

    managed_prometheus {
      enabled = true
    }

    advanced_datapath_observability_config {
      enable_metrics = true
      enable_relay   = true
    }
  }

  security_posture_config {
    mode               = "BASIC"
    vulnerability_mode = "VULNERABILITY_BASIC"
  }

  service_external_ips_config {
    enabled = false
  }

  maintenance_policy {
    recurring_window {
      start_time = "2025-01-05T09:00:00Z"
      end_time   = "2025-01-05T13:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
  }

  fleet {
    project = var.project_id
  }

  lifecycle {
    precondition {
      condition     = length(var.node_locations) >= 3
      error_message = "Regional production blueprints require at least three node locations."
    }
    precondition {
      condition     = var.private_endpoint_only || length(var.authorized_cidrs) > 0
      error_message = "A public control-plane endpoint requires at least one authorized CIDR."
    }
  }

  depends_on = [
    google_kms_crypto_key_iam_member.gke_service_agent,
    google_kms_crypto_key_iam_member.gke_backup_service_agent,
    google_project_iam_member.node_roles,
  ]

  timeouts {
    create = "60m"
    update = "60m"
    delete = "60m"
  }
}

resource "google_container_node_pool" "system" {
  provider = google-beta

  project            = var.project_id
  name               = "system"
  location           = var.region
  cluster            = google_container_cluster.this.name
  node_locations     = var.node_locations
  max_pods_per_node  = var.max_pods_per_node
  initial_node_count = max(1, ceil(var.system_min_nodes / length(var.node_locations)))
  deletion_policy    = var.deletion_protection ? "PREVENT" : "DELETE"

  autoscaling {
    total_min_node_count = var.system_min_nodes
    total_max_node_count = var.system_max_nodes
    location_policy      = "BALANCED"
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type    = var.system_machine_type
    image_type      = "COS_CONTAINERD"
    disk_type       = "pd-balanced"
    disk_size_gb    = 30
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    labels = merge(var.labels, {
      "workload-class" = "system"
    })
    resource_labels = var.labels
    tags            = ["gke-node", "gke-${var.cluster_name}", "gke-system"]

    metadata = {
      disable-legacy-endpoints = "true"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    gvnic {
      enabled = true
    }
  }

  depends_on = [google_container_cluster.this]
}

resource "google_container_node_pool" "general" {
  provider = google-beta

  project            = var.project_id
  name               = "general"
  location           = var.region
  cluster            = google_container_cluster.this.name
  node_locations     = var.node_locations
  max_pods_per_node  = var.max_pods_per_node
  initial_node_count = max(1, ceil(max(var.general_min_nodes, 1) / length(var.node_locations)))
  deletion_policy    = var.deletion_protection ? "PREVENT" : "DELETE"

  autoscaling {
    total_min_node_count = var.general_min_nodes
    total_max_node_count = var.general_max_nodes
    location_policy      = "BALANCED"
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 2
    max_unavailable = 0
  }

  node_config {
    machine_type    = var.general_machine_type
    image_type      = "COS_CONTAINERD"
    disk_type       = "pd-balanced"
    disk_size_gb    = 30
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    labels = merge(var.labels, {
      "workload-class" = "general"
    })
    resource_labels = var.labels
    tags            = ["gke-node", "gke-${var.cluster_name}", "gke-general"]

    metadata = {
      disable-legacy-endpoints = "true"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    gvnic {
      enabled = true
    }
  }

  depends_on = [google_container_cluster.this]
}

resource "google_container_node_pool" "gpu" {
  provider = google-beta
  count    = var.gpu.enabled ? 1 : 0

  project           = var.project_id
  name              = "h100"
  location          = var.region
  cluster           = google_container_cluster.this.name
  node_locations    = var.gpu.zones
  max_pods_per_node  = min(var.max_pods_per_node, 32)
  initial_node_count = max(1, var.gpu.minimum_nodes)
  deletion_policy    = var.deletion_protection ? "PREVENT" : "DELETE"

  autoscaling {
    total_min_node_count = var.gpu.minimum_nodes
    total_max_node_count = var.gpu.maximum_nodes
    location_policy      = var.gpu.provisioning_model == "reservation" ? "ANY" : "BALANCED"
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type    = var.gpu.machine_type
    image_type      = "COS_CONTAINERD"
    disk_type       = "pd-ssd"
    disk_size_gb    = 200
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    spot            = var.gpu.provisioning_model == "spot"
    flex_start      = var.gpu.provisioning_model == "flex-start"

    labels = merge(var.labels, {
      "workload-class" = "h100"
      "accelerator"    = var.gpu.model
    })
    resource_labels = var.labels
    tags            = ["gke-node", "gke-${var.cluster_name}", "gke-h100"]

    metadata = {
      disable-legacy-endpoints = "true"
    }

    guest_accelerator {
      type  = var.gpu.model
      count = var.gpu.accelerator_count

      gpu_driver_installation_config {
        gpu_driver_version = "LATEST"
      }
    }

    dynamic "reservation_affinity" {
      for_each = var.gpu.provisioning_model == "reservation" ? [1] : []
      content {
        consume_reservation_type = "SPECIFIC_RESERVATION"
        key                      = "compute.googleapis.com/reservation-name"
        values                   = [var.gpu.reservation_name]
      }
    }

    taint {
      key    = "nvidia.com/gpu"
      value  = "present"
      effect = "NO_SCHEDULE"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    gvnic {
      enabled = true
    }
  }

  depends_on = [google_container_cluster.this]
}
