provider "google" {
  region = var.region
}

locals {
  parent_id = var.platform_project_parent == null ? null : split("/", var.platform_project_parent)[1]
  state_bucket_name = coalesce(
    var.state_bucket_name,
    "${var.platform_project_id}-gke-factory-tfstate",
  )
  github_repository = "${var.github_owner}/${var.github_repository}"
  platform_apis = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "connectgateway.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "iap.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "sts.googleapis.com",
  ])
  project_roles = toset([
    "roles/artifactregistry.admin",
    "roles/cloudbuild.builds.editor",
    "roles/iam.serviceAccountAdmin",
    "roles/iap.admin",
    "roles/iam.serviceAccountUser",
    "roles/run.admin",
    "roles/secretmanager.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
  ])
  folder_roles = toset([
    "roles/artifactregistry.admin",
    "roles/binaryauthorization.policyAdmin",
    "roles/cloudkms.admin",
    "roles/compute.networkAdmin",
    "roles/container.admin",
    "roles/gkebackup.admin",
    "roles/gkehub.admin",
    "roles/gkehub.gatewayAdmin",
    "roles/gkehub.gatewayReader",
    "roles/iam.serviceAccountAdmin",
    "roles/resourcemanager.projectCreator",
    "roles/resourcemanager.projectIamAdmin",
    "roles/serviceusage.serviceUsageAdmin",
  ])
}

resource "google_project" "platform" {
  count = var.create_platform_project ? 1 : 0

  project_id      = var.platform_project_id
  name            = "GKE Cluster Factory"
  billing_account = var.billing_account
  folder_id       = var.platform_project_parent != null && startswith(var.platform_project_parent, "folders/") ? local.parent_id : null
  org_id          = var.platform_project_parent != null && startswith(var.platform_project_parent, "organizations/") ? local.parent_id : null
  labels = {
    managed-by = "gke-cluster-factory"
  }

  lifecycle {
    precondition {
      condition     = var.billing_account != null && var.platform_project_parent != null
      error_message = "Creating the platform project requires billing_account and platform_project_parent."
    }
  }
}

resource "google_project_service" "apis" {
  for_each = local.platform_apis

  project            = var.platform_project_id
  service            = each.value
  disable_on_destroy = false

  depends_on = [google_project.platform]
}

resource "google_storage_bucket" "terraform_state" {
  project                     = var.platform_project_id
  name                        = local.state_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  retention_policy {
    retention_period = 604800
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 20
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_artifact_registry_repository" "factory" {
  project       = var.platform_project_id
  location      = var.region
  repository_id = var.artifact_repository_name
  description   = "Container images for GKE Cluster Factory"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "github_token" {
  project   = var.platform_project_id
  secret_id = "gke-factory-github-token"

  replication {
    auto {}
  }

  labels = {
    managed-by = "gke-cluster-factory"
  }

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "github_actions" {
  project      = var.platform_project_id
  account_id   = "gke-factory-github"
  display_name = "GKE Factory GitHub Actions"
  description  = "Federated identity used by GitHub workflows to provision clusters"
}

resource "google_project_iam_member" "github_actions_project_roles" {
  for_each = local.project_roles

  project = var.platform_project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_folder_iam_member" "github_actions_cluster_folder_roles" {
  for_each = var.cluster_folder_id == null ? toset([]) : local.folder_roles

  folder = var.cluster_folder_id
  role   = each.value
  member = "serviceAccount:${google_service_account.github_actions.email}"
}

# When no folder is configured (standalone/personal projects with no org hierarchy),
# grant the same cluster-building roles directly on the platform project instead,
# since clusters in that case are provisioned in this same project.
resource "google_project_iam_member" "github_actions_cluster_project_roles" {
  for_each = var.cluster_folder_id == null ? setsubtract(local.folder_roles, ["roles/resourcemanager.projectCreator"]) : toset([])

  project = var.platform_project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_billing_account_iam_member" "github_actions_billing_user" {
  count = var.billing_account == null ? 0 : 1

  billing_account_id = var.billing_account
  role               = "roles/billing.user"
  member             = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_actions_xpn_admin" {
  count = var.shared_vpc_host_project_id == null ? 0 : 1

  project = var.shared_vpc_host_project_id
  role    = "roles/compute.xpnAdmin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.platform_project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "OIDC federation for ${local.github_repository}"
  disabled                  = false

  depends_on = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.platform_project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub repository provider"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
  }

  attribute_condition = "assertion.repository == '${local.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_federation" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.github_repository}"
}

resource "google_storage_bucket_iam_member" "state_admin" {
  bucket = google_storage_bucket.terraform_state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_actions.email}"
}
