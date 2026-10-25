# Example remote state. Copy and uncomment only after you own the bucket.
# Do not make remote state mandatory for local `terraform validate`.
#
# terraform {
#   backend "s3" {
#     bucket         = "your-terraform-state-bucket"
#     key            = "self-healing-devops-platform/terraform.tfstate"
#     region         = "eu-west-2"
#     dynamodb_table = "your-terraform-locks"
#     encrypt        = true
#   }
# }
