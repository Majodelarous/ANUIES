output "ip" {
  description = "IP fija del servidor (Elastic IP)."
  value       = aws_eip.rous.public_ip
}

output "dominio" {
  value = var.dominio
}

output "panel" {
  description = "Liga del panel (pide la contraseña de PANEL_CLAVE_HASH)."
  value       = "https://${var.dominio}/control"
}

output "instancia" {
  value = aws_instance.rous.id
}

output "ssh" {
  value = "ssh ubuntu@${aws_eip.rous.public_ip}"
}

output "tunel" {
  description = "Plan B si el dominio falla: túnel SSH y luego http://127.0.0.1:7861/control"
  value       = "ssh -N -L 7861:127.0.0.1:7861 ubuntu@${aws_eip.rous.public_ip}"
}

output "sin_ssh" {
  description = "Entrar por Session Manager si cambió tu IP (requiere el plugin de Session Manager)."
  value       = "aws ssm start-session --target ${aws_instance.rous.id} --region ${var.region} --profile ${var.perfil_aws}"
}
