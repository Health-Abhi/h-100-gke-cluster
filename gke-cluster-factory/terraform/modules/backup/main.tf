resource "google_gke_backup_backup_plan" "this" {
  project     = var.project_id
  name        = substr("${var.cluster_name}-backup", 0, 63)
  cluster     = var.cluster_id
  location    = var.region
  description = "Managed backup plan for ${var.cluster_name}"
  labels      = var.labels

  deletion_policy = var.deletion_protection ? "PREVENT" : "DELETE"

  retention_policy {
    backup_delete_lock_days = var.delete_lock_days
    backup_retain_days      = var.retention_days
  }

  backup_schedule {
    rpo_config {
      target_rpo_minutes = var.target_rpo_minutes
    }
  }

  backup_config {
    include_volume_data = var.include_volume_data
    include_secrets     = var.include_secrets
    all_namespaces      = true

    encryption_key {
      gcp_kms_encryption_key = var.kms_key_id
    }
  }
}
