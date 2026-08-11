provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_service_account" "portal" {
  project      = var.project_id
  account_id   = "gke-factory-portal"
  display_name = "GKE Cluster Factory portal"
  description  = "Runtime identity for the self-service portal"
}

resource "google_secret_manager_secret_iam_member" "github_token" {
  project   = var.project_id
  secret_id = var.github_token_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.portal.email}"
}

resource "google_cloud_run_v2_service" "portal" {
  project             = var.project_id
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  iap_enabled         = true
  deletion_protection = var.deletion_protection

  template {
    service_account                  = google_service_account.portal.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    timeout                          = "60s"
    max_instance_request_concurrency = 40

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = var.container_image

      ports {
        name           = "http1"
        container_port = 8080
      }

      env {
        name  = "FACTORY_STORAGE_MODE"
        value = "github"
      }
      env {
        name  = "FACTORY_GITHUB_OWNER"
        value = var.github_owner
      }
      env {
        name  = "FACTORY_GITHUB_REPOSITORY"
        value = var.github_repository
      }
      env {
        name  = "FACTORY_GITHUB_DEFAULT_BRANCH"
        value = var.github_default_branch
      }
      env {
        name  = "FACTORY_ENVIRONMENT"
        value = "production"
      }
      env {
        name = "FACTORY_GITHUB_TOKEN"
        value_source {
          secret_key_ref {
            secret  = var.github_token_secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      startup_probe {
        initial_delay_seconds = 1
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 12
        http_get {
          path = "/readyz"
          port = 8080
        }
      }

      liveness_probe {
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3
        http_get {
          path = "/healthz"
          port = 8080
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_iam_member.github_token]
}

resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.portal.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

resource "google_iap_web_cloud_run_service_iam_member" "portal_user" {
  project                = var.project_id
  location               = var.region
  cloud_run_service_name = google_cloud_run_v2_service.portal.name
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = "${var.iam_principal_type}:${var.invoker_group}"

  depends_on = [google_cloud_run_v2_service_iam_member.iap_invoker]
}
