variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-west1"
}
variable "service_name" {
  type    = string
  default = "gke-cluster-factory"
}
variable "container_image" {
  description = "Immutable Artifact Registry image reference, preferably by digest."
  type        = string
}
variable "github_owner" { type = string }
variable "github_repository" { type = string }
variable "github_default_branch" {
  type    = string
  default = "main"
}
variable "github_token_secret_id" {
  type    = string
  default = "gke-factory-github-token"
}
variable "invoker_group" {
  description = "Google group (or individual account, if iam_principal_type is \"user\") allowed to use the private Cloud Run portal."
  type        = string
}
variable "iam_principal_type" {
  description = "IAM principal prefix for invoker_group: \"group\" for a real Google Group, \"user\" for an individual account (e.g. personal Gmail with no org)."
  type        = string
  default     = "group"
  validation {
    condition     = contains(["group", "user"], var.iam_principal_type)
    error_message = "iam_principal_type must be \"group\" or \"user\"."
  }
}
variable "deletion_protection" {
  type    = bool
  default = true
}
