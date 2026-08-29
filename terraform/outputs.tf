output "namespace_name" {
  description = "Managed Kubernetes namespace"
  value       = kubernetes_namespace_v1.research_platform.metadata[0].name
}

output "namespace_uid" {
  description = "Kubernetes UID assigned to the namespace"
  value       = kubernetes_namespace_v1.research_platform.metadata[0].uid
}
