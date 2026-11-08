output "ip" {
  description = "IP pública del servidor (cambia si la instancia se detiene y se vuelve a encender)."
  value       = aws_instance.rous.public_ip
}

output "instancia" {
  value = aws_instance.rous.id
}

output "ssh" {
  value = "ssh ubuntu@${aws_instance.rous.public_ip}"
}

output "panel" {
  description = "Abre el túnel y luego entra a http://127.0.0.1:7861 en tu navegador."
  value       = "ssh -N -L 7861:127.0.0.1:7861 ubuntu@${aws_instance.rous.public_ip}"
}

output "sin_ssh" {
  description = "Entrar por Session Manager si cambió tu IP (requiere el plugin de Session Manager)."
  value       = "aws ssm start-session --target ${aws_instance.rous.id} --region ${var.region} --profile ${var.perfil_aws}"
}
