output "network_self_link" {
  value = local.network_id
}

output "subnetwork_self_link" {
  value = google_compute_subnetwork.gke.id
}

output "subnetwork_name" {
  value = google_compute_subnetwork.gke.name
}
