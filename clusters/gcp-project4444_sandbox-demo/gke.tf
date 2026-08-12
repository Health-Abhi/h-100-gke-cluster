module "gke" {
  source = "../../terraform/cluster"
  project_id = "gcp-project4444"
  cluster_name = "sandbox-demo"
  region = "us-west3"
  env-type = "nonprod"
  description = "creating new psc cluster with cloudbuild"
  network_project_id = "h100-sandbox-np-001-vpc-usw3"
  network = "001-vpc-usw3"
  subnetwork = "san-sandbox"
  cluster_resource_labels = {
    costcenter = "150001"
    owner = "platform"
    lineofbusiness = "h100-spltyrx"
  }
  node_pools = [
    {
      name = "default-node-pool"
      machine_type = "n2d-standard-8"
      min_count = 1
      max_count = 20
      image_type = "COS_CONTAINERD"
      auto_repair = true
      auto_upgrade = true
      preemptible = false
      initial_node_count = 1
      enable_secure_boot = true
    }
  ]
  node_pools_oauth_scopes = {
    all = [
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/servicecontrol",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/trace.append"
    ]
  }
  node_pools_labels = {
    all = {}
  }
  node_pools_metadata = {
    all = {
      serial-port-logging-enable = false
    }
  }
  node_pools_tags = {
    all = []
  }
  node_pools_taints = {
    all = []
  }
}

terraform {
  required_version = ">= 1.0.8"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "<= 6.42.0"
    }

    google-beta = {
      source  = "hashicorp/google-beta"
      version = "<= 6.42.0"
    }

    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.0.0"
    }
  }
# Istio internal IP address: 10.0.11.1
# Istio internal proxy IP address for external LB: 10.0.0.10
}
