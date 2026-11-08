terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.perfil_aws

  default_tags {
    tags = {
      Proyecto     = "rous"
      Administrado = "terraform"
    }
  }
}
