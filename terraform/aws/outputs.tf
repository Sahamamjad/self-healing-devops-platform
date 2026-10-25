output "vpc_id" {
  value       = aws_vpc.this.id
  description = "VPC ID. Populated only after an authorized apply."
}

output "private_subnet_ids" {
  value       = aws_subnet.private[*].id
  description = "Private subnets used by the managed node group."
}

output "cluster_name" {
  value       = aws_eks_cluster.this.name
  description = "EKS cluster name."
}

output "cluster_endpoint" {
  value       = aws_eks_cluster.this.endpoint
  description = "EKS API endpoint. With the default private-only setting this is reachable from inside the VPC, not from a laptop."
}

output "cost_warning" {
  value       = "Do not apply without explicit authorization. A default apply creates a paid EKS control plane, NAT gateway, public IPv4 address, worker node, EBS volumes, and CloudWatch logs. validate and plan do not create these resources."
  description = "Cost warning. This output is a reminder, not a bill."
}
