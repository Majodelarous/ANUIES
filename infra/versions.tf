terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.26"
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

# El token se lee de la variable de entorno CLOUDFLARE_API_TOKEN (permiso: Zona, DNS, Editar,
# solo para la zona del dominio). No va en archivos del repositorio.
provider "cloudflare" {}
