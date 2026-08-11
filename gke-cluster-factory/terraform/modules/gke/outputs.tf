output "cluster_id" {
  value = google_container_cluster.this.id
}

output "cluster_name" {
  value = google_container_cluster.this.name
}

output "kms_key_id" {
  value = google_kms_crypto_key.gke.id
}

output "node_service_account" {
  value = google_service_account.nodes.email
}

output "fleet_membership" {
  value = google_container_cluster.this.fleet[0].membership_id
}
