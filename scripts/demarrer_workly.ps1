# Démarre le point d'accès de Workly ET le tunnel ngrok, avec tous les réglages.
#
#   powershell -ExecutionPolicy Bypass -File scripts\demarrer_workly.ps1
#
# Le jeton est lu dans un fichier (jamais écrit dans ce script). Les réglages d'alerte e-mail
# viennent de scripts\configurer_alertes.ps1. Arrêt : Ctrl+C dans cette fenêtre, puis fermer la
# fenêtre ngrok.
param(
    [string]$FichierJeton = "$HOME\Desktop\jeton-workly.txt",
    [string]$DomaineNgrok = "condone-dragonfly-coveting.ngrok-free.dev",
    [int]$Port = 8765
)

$racine = Split-Path -Parent $PSScriptRoot
Set-Location $racine

if (-not (Test-Path $FichierJeton)) {
    Write-Host "Fichier du jeton introuvable : $FichierJeton" -ForegroundColor Red
    Read-Host "Appuyez sur Entree pour fermer"
    exit 1
}
$env:WORKLY_TOKEN_TACHES = (Get-Content $FichierJeton -Raw).Trim()

# Réglages d'alerte e-mail enregistrés une fois par configurer_alertes.ps1
foreach ($nom in "WORKLY_SMTP_UTILISATEUR", "WORKLY_SMTP_MOT_DE_PASSE",
    "WORKLY_ALERTE_DESTINATAIRE", "WORKLY_SMTP_PORT") {
    $valeur = [Environment]::GetEnvironmentVariable($nom, "User")
    if ($valeur) { Set-Item -Path "Env:$nom" -Value $valeur }
}
if (-not $env:WORKLY_SMTP_MOT_DE_PASSE) {
    Write-Host "Alertes e-mail non configurees (voir scripts\configurer_alertes.ps1)." -ForegroundColor Yellow
}

$activation = Join-Path $racine ".venv\Scripts\Activate.ps1"
if (Test-Path $activation) { . $activation }

# Tunnel ngrok dans sa propre fenêtre
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "ngrok http $Port --url https://$DomaineNgrok"

python -m app.taches serveur --port $Port
