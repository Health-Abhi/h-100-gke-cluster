variable "platform_project_id" { type = string }
variable "create_platform_project" {
  type    = bool
  default = false
}
variable "platform_project_parent" {
  description = "Parent such as folders/123456789."
  type        = string
  default     = null
}
variable "billing_account" {
  type    = string
  default = null
}
variable "cluster_folder_id" {
  description = "Numeric folder ID where cluster service projects are created."
  type        = string
  default     = null
}
variable "shared_vpc_host_project_id" {
  type    = string
  default = null
}
variable "region" {
  type    = string
  default = "us-west1"
}
variable "github_owner" { type = string }
variable "github_repository" { type = string }
variable "state_bucket_name" {
  type    = string
  default = null
}
variable "artifact_repository_name" {
  type    = string
  default = "gke-cluster-factory"
}
