terraform {
  required_version = ">= 1.6.0, < 1.18.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "self-healing-devops-platform"
      ManagedBy   = "terraform"
      Environment = "optional-demo"
    }
  }
}
