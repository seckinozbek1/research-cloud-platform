terraform {
  required_version = ">= 1.16.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}

resource "kubernetes_namespace_v1" "research_platform" {
  metadata {
    name = var.namespace_name

    labels = {
      environment = var.environment
      purpose     = "research"
    }
  }
}
