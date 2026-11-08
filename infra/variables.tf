variable "region" {
  description = "Región de AWS. us-east-1 tiene Nova Sonic."
  type        = string
  default     = "us-east-1"
}

variable "perfil_aws" {
  description = "Perfil de ~/.aws/config con el que corre Terraform."
  type        = string
  default     = "Fortino-IAM-Admin"
}

variable "nombre" {
  description = "Prefijo de los recursos."
  type        = string
  default     = "rous"
}

variable "tipo_instancia" {
  description = "t3.small (2 GB, x86). t3.micro (1 GB) se queda corta para el bot de voz y el puente."
  type        = string
  default     = "t3.small"
}

variable "disco_gb" {
  description = "Disco raíz gp3. Las imágenes ocupan unos 3 GB y la construcción necesita espacio extra."
  type        = number
  default     = 30
}

variable "mi_ip" {
  description = "IP pública desde la que se entra por SSH, en formato CIDR (por ejemplo 189.203.10.20/32)."
  type        = string

  validation {
    condition     = can(cidrhost(var.mi_ip, 0)) && var.mi_ip != "0.0.0.0/0"
    error_message = "Usa tu IP con /32 (consulta: curl -s https://checkip.amazonaws.com). No se permite 0.0.0.0/0."
  }
}

variable "llave_publica" {
  description = "Ruta de la llave pública SSH que se instala en el servidor."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "repositorio" {
  description = "Repositorio público de donde el servidor baja el código."
  type        = string
  default     = "https://github.com/Majodelarous/ANUIES.git"
}

variable "rama" {
  description = "Rama que se despliega."
  type        = string
  default     = "panel-control"
}

variable "dominio" {
  description = "Dominio del panel. En Cloudflare: registro A hacia la IP fija, sin proxy (nube gris)."
  type        = string
  default     = "rous.foor.dev"
}

variable "permitir_nova" {
  description = "Da permiso a la instancia para usar Nova Sonic en Bedrock, sin llaves de AWS en el .env."
  type        = bool
  default     = true
}
