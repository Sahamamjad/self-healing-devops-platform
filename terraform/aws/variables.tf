variable "aws_region" {
  type        = string
  description = "AWS region for the optional stack."
  default     = "eu-west-2"
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name."
  default     = "self-healing-demo"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR. Must be large enough for two public and two private /20 subnets."
  default     = "10.42.0.0/16"
}

variable "kubernetes_version" {
  type        = string
  description = "EKS Kubernetes version. 1.34 appeared in the Amazon EKS standard-support list on 2026-10-21. Confirm the current list before apply."
  default     = "1.34"
}

variable "enable_cluster_public_endpoint" {
  type        = bool
  description = "Private API endpoint is always enabled. Public access stays off unless this is true."
  default     = false
}

variable "authorized_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to reach the public cluster endpoint. Required when public access is enabled. Do not use 0.0.0.0/0."
  default     = []

  validation {
    condition     = alltrue([for cidr in var.authorized_cidrs : cidr != "0.0.0.0/0"])
    error_message = "authorized_cidrs must not contain 0.0.0.0/0."
  }
}

variable "node_instance_type" {
  type        = string
  description = "Worker instance type. t3.small is a small demo size, not a production recommendation."
  default     = "t3.small"
}

variable "node_min_size" {
  type        = number
  description = "Managed node group minimum."
  default     = 1
}

variable "node_desired_size" {
  type        = number
  description = "Managed node group desired size. One node is not highly available."
  default     = 1
}

variable "node_max_size" {
  type        = number
  description = "Managed node group maximum."
  default     = 2
}
