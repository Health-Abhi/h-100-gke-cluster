output "cluster_id" {
  value = module.gke.cluster_id
}

output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_location" {
  value = var.region
}

output "project_id" {
  value = var.project_id
}

output "fleet_membership" {
  value = module.gke.fleet_membership
}

output "connect_gateway_command" {
  value = "gcloud container fleet memberships get-credentials ${module.gke.fleet_membership} --project ${var.project_id} --location ${var.region}"
}

output "backup_plan_id" {
  value = try(module.backup[0].backup_plan_id, null)
}
