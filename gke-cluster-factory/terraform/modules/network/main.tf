data "google_project" "service" {
  project_id = var.service_project_id
}

resource "google_compute_network" "dedicated" {
  count = var.mode == "dedicated" ? 1 : 0

  project                 = var.network_project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"
  mtu                     = 1460
}

data "google_compute_network" "shared" {
  count = var.mode == "shared" ? 1 : 0

  project = var.network_project_id
  name    = var.network_name
}

locals {
  network_id = var.mode == "dedicated" ? google_compute_network.dedicated[0].id : data.google_compute_network.shared[0].id
  is_shared  = var.mode == "shared" && var.service_project_id != var.network_project_id
}

resource "google_compute_subnetwork" "gke" {
  project                  = var.network_project_id
  name                     = var.subnet_name
  region                   = var.region
  network                  = local.network_id
  ip_cidr_range            = var.node_cidr
  private_ip_google_access = true
  stack_type               = "IPV4_ONLY"

  secondary_ip_range {
    range_name    = var.pod_range_name
    ip_cidr_range = var.pod_cidr
  }

  secondary_ip_range {
    range_name    = var.service_range_name
    ip_cidr_range = var.service_cidr
  }
}

resource "google_compute_shared_vpc_service_project" "attachment" {
  count = local.is_shared ? 1 : 0

  host_project    = var.network_project_id
  service_project = var.service_project_id
}

resource "google_compute_subnetwork_iam_member" "gke_service_agent" {
  count = local.is_shared ? 1 : 0

  project    = var.network_project_id
  region     = var.region
  subnetwork = google_compute_subnetwork.gke.name
  role       = "roles/compute.networkUser"
  member     = "serviceAccount:service-${data.google_project.service.number}@container-engine-robot.iam.gserviceaccount.com"
}

resource "google_compute_subnetwork_iam_member" "cloud_services_agent" {
  count = local.is_shared ? 1 : 0

  project    = var.network_project_id
  region     = var.region
  subnetwork = google_compute_subnetwork.gke.name
  role       = "roles/compute.networkUser"
  member     = "serviceAccount:${data.google_project.service.number}@cloudservices.gserviceaccount.com"
}

resource "google_project_iam_member" "host_service_agent_user" {
  count = local.is_shared ? 1 : 0

  project = var.network_project_id
  role    = "roles/container.hostServiceAgentUser"
  member  = "serviceAccount:service-${data.google_project.service.number}@container-engine-robot.iam.gserviceaccount.com"
}

resource "google_compute_router" "nat" {
  count = var.create_nat ? 1 : 0

  project = var.network_project_id
  name    = "cr-${substr(var.subnet_name, 0, 50)}"
  region  = var.region
  network = local.network_id
}

resource "google_compute_router_nat" "nat" {
  count = var.create_nat ? 1 : 0

  project                            = var.network_project_id
  name                               = "nat-${substr(var.subnet_name, 0, 49)}"
  router                             = google_compute_router.nat[0].name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.gke.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
