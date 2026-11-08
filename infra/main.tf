# Una instancia EC2 con Docker que corre docker-compose.yml tal cual.
# SSH solo desde tu IP. El panel queda en https://<dominio> con contraseña, detrás de Caddy.

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_vpc" "predeterminada" {
  default = true
}

resource "aws_security_group" "rous" {
  name        = "${var.nombre}-ssh"
  description = "SSH desde la IP de quien administra y HTTPS para el panel"
  vpc_id      = data.aws_vpc.predeterminada.id
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.rous.id
  description       = "SSH"
  cidr_ipv4         = var.mi_ip
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

# 80 y 443 abiertos a todos: el panel pide contraseña y Caddy sirve HTTPS (el 80 solo redirige
# y sirve el reto de Let's Encrypt)
resource "aws_vpc_security_group_ingress_rule" "web" {
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.rous.id
  description       = "Panel por HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
}

resource "aws_vpc_security_group_ingress_rule" "http3" {
  security_group_id = aws_security_group.rous.id
  description       = "Panel por HTTP/3"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "udp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "salida" {
  security_group_id = aws_security_group.rous.id
  description       = "WhatsApp, motores de voz, GitHub y paquetes"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_key_pair" "rous" {
  key_name   = "${var.nombre}-llave"
  public_key = file(pathexpand(var.llave_publica))
}

# Rol de la instancia: Session Manager (entrar sin SSH si cambia tu IP) y, si se pide, Nova Sonic.
data "aws_iam_policy_document" "confianza" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rous" {
  name               = "${var.nombre}-instancia"
  assume_role_policy = data.aws_iam_policy_document.confianza.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.rous.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "nova" {
  statement {
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:InvokeModelWithBidirectionalStream",
    ]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/amazon.nova-*"]
  }
}

resource "aws_iam_role_policy" "nova" {
  count  = var.permitir_nova ? 1 : 0
  name   = "nova-sonic"
  role   = aws_iam_role.rous.id
  policy = data.aws_iam_policy_document.nova.json
}

resource "aws_iam_instance_profile" "rous" {
  name = "${var.nombre}-instancia"
  role = aws_iam_role.rous.name
}

resource "aws_instance" "rous" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.tipo_instancia
  key_name                    = aws_key_pair.rous.key_name
  vpc_security_group_ids      = [aws_security_group.rous.id]
  iam_instance_profile        = aws_iam_instance_profile.rous.name
  associate_public_ip_address = true

  user_data = templatefile("${path.module}/arranque.sh.tftpl", {
    repositorio = var.repositorio
    rama        = var.rama
  })
  user_data_replace_on_change = true

  metadata_options {
    http_tokens = "required"
    # 2 saltos: los contenedores llegan a las credenciales del rol (para Nova sin llaves)
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.disco_gb
    encrypted   = true
  }

  credit_specification {
    # standard: si se agotan los créditos de CPU la instancia va más lenta, pero no cobra extra
    cpu_credits = "standard"
  }

  tags = {
    Name = var.nombre
  }

  lifecycle {
    ignore_changes = [ami]
  }
}

# IP fija: el registro A de Cloudflare no cambia aunque la instancia se reinicie
resource "aws_eip" "rous" {
  domain   = "vpc"
  instance = aws_instance.rous.id

  tags = {
    Name = var.nombre
  }
}
