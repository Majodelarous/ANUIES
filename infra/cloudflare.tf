# Registro DNS del panel: lo crea el apply y lo borra el destroy, así nunca queda una IP vieja
# (Let's Encrypt valida contra todas las IP del nombre y una IP muerta hace fallar el certificado).

data "cloudflare_zone" "zona" {
  filter = {
    name = var.zona_cloudflare
  }
}

resource "cloudflare_dns_record" "panel" {
  zone_id = data.cloudflare_zone.zona.zone_id
  name    = var.dominio
  type    = "A"
  content = aws_eip.rous.public_ip
  # Sin proxy: Caddy recibe la conexión directa y saca el certificado de Let's Encrypt
  proxied = false
  ttl     = 60
  comment = "Panel de Rous (Terraform, infra/)"
}
