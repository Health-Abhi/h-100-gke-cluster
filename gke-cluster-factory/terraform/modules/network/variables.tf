variable "service_project_id" { type = string }
variable "network_project_id" { type = string }
variable "region" { type = string }
variable "mode" {
  type = string
  validation {
    condition     = contains(["dedicated", "shared"], var.mode)
    error_message = "mode must be dedicated or shared."
  }
}
variable "network_name" { type = string }
variable "subnet_name" { type = string }
variable "node_cidr" { type = string }
variable "pod_cidr" { type = string }
variable "service_cidr" { type = string }
variable "pod_range_name" { type = string }
variable "service_range_name" { type = string }
variable "create_nat" { type = bool }
