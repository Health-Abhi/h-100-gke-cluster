variable "cluster_name" {
  description = "GKE cluster name."
  type        = string
}

variable "project_id" {
  description = "Google Cloud service project that owns the cluster."
  type        = string
}

variable "create_project" {
  description = "Create the service project before provisioning the cluster."
  type        = bool
  default     = false
}

variable "project_parent" {
  description = "Parent for a newly created project, for example folders/123456789."
  type        = string
  default     = null
}

variable "billing_account" {
  description = "Billing account for a newly created project."
  type        = string
  default     = null
}

variable "region" {
  type    = string
  default = "us-west1"
}

variable "node_locations" {
  type = list(string)
  default = [
    "us-west1-a",
    "us-west1-b",
    "us-west1-c",
  ]
}

variable "environment" {
  type = string
}

variable "blueprint" {
  type = string
}

variable "owner_group" {
  type = string
}

variable "gke_security_group" {
  description = "Cloud Identity group-of-groups used by Google Groups for GKE RBAC."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+$", var.gke_security_group))
    error_message = "gke_security_group must be an email address."
  }
}

variable "platform_admin_group" {
  description = "Google group granted Kubernetes cluster-admin by the GitOps baseline."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+$", var.platform_admin_group))
    error_message = "platform_admin_group must be an email address."
  }
}

variable "iam_principal_type" {
  description = "IAM principal prefix for owner_group/platform_admin_group bindings: \"group\" for real Google Groups (Cloud Identity/Workspace), \"user\" for an individual account (e.g. personal Gmail with no org)."
  type        = string
  default     = "group"
  validation {
    condition     = contains(["group", "user"], var.iam_principal_type)
    error_message = "iam_principal_type must be \"group\" or \"user\"."
  }
}

variable "enable_google_groups_rbac" {
  description = "Enable GKE's Google Groups for RBAC. Requires a Cloud Identity/Workspace domain — set false for personal/non-org projects."
  type        = bool
  default     = true
}

variable "technical_contact" {
  type = string
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "release_channel" {
  type    = string
  default = "REGULAR"
}

variable "system_machine_type" {
  type    = string
  default = "e2-standard-4"
}

variable "general_machine_type" {
  type    = string
  default = "n2-standard-8"
}

variable "capacity" {
  type = object({
    system_min_nodes  = number
    system_max_nodes  = number
    general_min_nodes = number
    general_max_nodes = number
    max_pods_per_node = number
  })
}

variable "network" {
  type = object({
    mode                  = string
    host_project_id       = optional(string)
    network_name          = string
    create_nat            = bool
    private_endpoint_only = bool
    authorized_cidrs      = list(string)
    node_cidr             = string
    pod_cidr              = string
    service_cidr          = string
    control_plane_cidr    = string
    subnet_name           = string
    pod_range_name        = string
    service_range_name    = string
  })
}

variable "gpu" {
  type = object({
    enabled            = bool
    model              = optional(string)
    machine_type       = optional(string)
    accelerator_count  = number
    minimum_nodes      = number
    maximum_nodes      = number
    zones              = list(string)
    provisioning_model = string
    reservation_name   = optional(string)
  })
}

variable "backup" {
  type = object({
    tier                = string
    retention_days      = number
    delete_lock_days    = number
    target_rpo_minutes  = number
    include_volume_data = bool
    include_secrets     = bool
  })
}

variable "deletion_protection" {
  type    = bool
  default = true
}
