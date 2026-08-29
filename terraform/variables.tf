variable "namespace_name" {
  description = "Kubernetes namespace managed by Terraform"
  type        = string
  default     = "research-platform"
}

variable "environment" {
  description = "Environment label"
  type        = string
  default     = "local"
}
