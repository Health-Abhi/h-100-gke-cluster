provider "google" {
  region = var.region
}

provider "google-beta" {
  region = var.region
}

provider "google" {
  alias   = "network"
  project = local.network_project_id
  region  = var.region
}
