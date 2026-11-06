<#
Atajos de Rous en Docker para Windows (PowerShell). Equivale a los comandos de docker compose.

  .\rous.ps1 arriba                 construye y levanta todo
  .\rous.ps1 qr                     muestra el QR para vincular WhatsApp (Ctrl+C para salir)
  .\rous.ps1 estado                 qué servicios están corriendo
  .\rous.ps1 logs [servicio]        registro en vivo (bot, puente, programador, panel)
  .\rous.ps1 panel                  abre el panel de la familia
  .\rous.ps1 persona -Nombre "Amada López" -Trato abuelita -Telefono 522221234567 [-Consentimiento]
  .\rous.ps1 personas               lista las personas registradas
  .\rous.ps1 llamar [numero]        Rous llama ahora (sin número: WHATSAPP_PERSONA)
  .\rous.ps1 colgar                 cuelga y libera el puente
  .\rous.ps1 motor gemini|nova|openai
  .\rous.ps1 respaldo               copia datos y sesión de WhatsApp a la carpeta respaldos
  .\rous.ps1 vincular               quita la sesión de WhatsApp para vincular otro número
  .\rous.ps1 abajo                  detiene todo (los datos se conservan)

Si Windows no deja ejecutar scripts, una sola vez:
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#>
param(
    [Parameter(Position = 0)] [string] $Comando = "ayuda",
    [Parameter(Position = 1)] [string] $Valor = "",
    [string] $Nombre, [string] $Trato, [string] $Telefono, [string] $Contacto,
    [switch] $Consentimiento
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$envFile = if ($env:ROUS_ENV) { $env:ROUS_ENV } else { "agente/.env" }

function Revisar-Env {
    if (-not (Test-Path $envFile)) {
        Write-Host "Falta $envFile. Cópialo de agente/.env.example y llena tus llaves y números:" -ForegroundColor Yellow
        Write-Host "  Copy-Item agente/.env.example agente/.env ; notepad agente/.env"
        exit 1
    }
}

switch ($Comando) {
    "arriba"   { Revisar-Env; docker compose up -d --build; docker compose ps }
    "qr"       { docker compose logs -f --no-log-prefix --tail 60 puente }
    "estado"   { docker compose ps }
    "logs"     { if ($Valor) { docker compose logs -f --tail 100 $Valor } else { docker compose logs -f --tail 100 } }
    "panel"    { Start-Process "http://127.0.0.1:7861" }
    "persona"  {
        if (-not $Nombre -or -not $Trato) { Write-Host 'Uso: .\rous.ps1 persona -Nombre "Amada López" -Trato abuelita -Telefono 522221234567 [-Consentimiento]'; exit 1 }
        $args2 = @("compania-semilla", "--nombre", $Nombre, "--trato", $Trato)
        if ($Telefono) { $args2 += @("--telefono", $Telefono) }
        if ($Contacto) { $args2 += @("--contacto", $Contacto) }
        if ($Consentimiento) { $args2 += "--consentimiento" }
        docker compose run --rm bot @args2
    }
    "personas" { docker compose run --rm bot compania-datos personas }
    "llamar"   { if ($Valor) { docker compose exec bot compania-llamar-wa $Valor } else { docker compose exec bot compania-llamar-wa } }
    "colgar"   { docker compose exec bot compania-llamar-wa --colgar }
    "motor"    {
        if ($Valor -notin @("gemini", "nova", "openai")) { Write-Host "Uso: .\rous.ps1 motor gemini|nova|openai"; exit 1 }
        Revisar-Env
        $texto = Get-Content $envFile -Raw
        # En Docker no existe el perfil de AWS de la laptop: Nova necesita las llaves en el .env
        $llave = @{ gemini = "GOOGLE_API_KEY"; openai = "OPENAI_API_KEY"; nova = "AWS_ACCESS_KEY_ID" }[$Valor]
        if ($texto -notmatch "(?m)^$llave=\S+") {
            Write-Host "Falta $llave en $envFile. Ponla antes de cambiar el motor a $Valor." -ForegroundColor Yellow
            exit 1
        }
        if ($texto -match "(?m)^MOTOR_VOZ=.*$") { $texto = $texto -replace "(?m)^MOTOR_VOZ=.*$", "MOTOR_VOZ=$Valor" } else { $texto += "`nMOTOR_VOZ=$Valor`n" }
        [IO.File]::WriteAllText((Resolve-Path $envFile), $texto)
        docker compose up -d
        Write-Host "Motor de voz: $Valor (se reiniciaron los servicios)"
    }
    "respaldo" {
        $fecha = Get-Date -Format "yyyyMMdd-HHmmss"
        New-Item -ItemType Directory -Force -Path respaldos | Out-Null
        docker compose run --rm --no-deps -v "${PWD}/respaldos:/respaldos" bot sh -c "tar czf /respaldos/datos-$fecha.tgz -C /datos ."
        docker compose run --rm --no-deps -v "${PWD}/respaldos:/respaldos" puente sh -c "tar czf /respaldos/whatsapp-$fecha.tgz -C /auth ."
        Write-Host "Respaldo en respaldos\datos-$fecha.tgz y respaldos\whatsapp-$fecha.tgz"
    }
    "vincular" {
        $ok = Read-Host "Esto quita la sesión de WhatsApp actual (se respalda antes). Escribe si para seguir"
        if ($ok -ne "si") { exit 0 }
        & $PSCommandPath respaldo
        docker compose stop puente
        docker compose run --rm --no-deps puente sh -c "rm -rf /auth/* /auth/.[!.]*"
        docker compose up -d puente
        Write-Host "Escanea el QR desde WhatsApp > Dispositivos vinculados del número de la asistente."
        docker compose logs -f --no-log-prefix --tail 60 puente
    }
    "abajo"    { docker compose down }
    default    { Get-Help $PSCommandPath -Detailed | Select-Object -ExpandProperty description; Get-Content $PSCommandPath -TotalCount 22 | Select-Object -Skip 1 }
}
