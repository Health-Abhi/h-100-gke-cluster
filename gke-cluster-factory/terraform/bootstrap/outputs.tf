output "terraform_state_bucket" {
  value = google_storage_bucket.terraform_state.name
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.factory.id
}

output "github_actions_service_account" {
  value = google_service_account.github_actions.email
}

output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "github_token_secret_id" {
  value = google_secret_manager_secret.github_token.id
}

output "next_step_add_github_token" {
  value = "printf '%s' 'YOUR_TOKEN' | gcloud secrets versions add gke-factory-github-token --data-file=- --project ${var.platform_project_id}"
}
