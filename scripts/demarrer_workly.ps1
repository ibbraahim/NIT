# Démarre le point d'accès de Workly ET le tunnel ngrok, avec tous les réglages.
#
#   powershell -ExecutionPolicy Bypass -File scripts\demarrer_workly.ps1
#
# Option -SansNgrok : ne lance que le serveur (ngrok déjà ouvert dans un autre terminal).
# Le jeton est lu dans un fichier (jamais écrit dans ce script). Les réglages d'alerte e-mail
# viennent de scripts\configurer_alertes.ps1. Arrêt : Ctrl+C dans cette fenêtre, puis fermer la
# fenêtre ngrok.
param(
    [switch]$SansNgrok,
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

# Réglages d'alerte e-mail (configurer_alertes.ps1) et de connexion Odoo, enregistrés une fois
# dans les variables d'environnement de l'utilisateur
foreach ($nom in "WORKLY_SMTP_UTILISATEUR", "WORKLY_SMTP_MOT_DE_PASSE",
    "WORKLY_ALERTE_DESTINATAIRE", "WORKLY_SMTP_PORT",
    "WORKLY_ODOO_URL", "WORKLY_ODOO_BASE", "WORKLY_ODOO_UTILISATEUR", "WORKLY_ODOO_CLE") {
    $valeur = [Environment]::GetEnvironmentVariable($nom, "User")
    if ($valeur) { Set-Item -Path "Env:$nom" -Value $valeur }
}
if (-not $env:WORKLY_SMTP_MOT_DE_PASSE) {
    Write-Host "Alertes e-mail non configurees (voir scripts\configurer_alertes.ps1)." -ForegroundColor Yellow
}

$activation = Join-Path $racine ".venv\Scripts\Activate.ps1"
if (Test-Path $activation) { . $activation }

# Tunnel ngrok dans sa propre fenêtre (option -SansNgrok si vous le lancez vous-même).
# Un seul ngrok peut servir ce domaine : s'il en tourne déjà un, on n'en démarre pas un second.
if ($SansNgrok) {
    Write-Host "ngrok non lance (option -SansNgrok)." -ForegroundColor Yellow
} elseif (Get-Process ngrok -ErrorAction SilentlyContinue) {
    Write-Host "ngrok tourne deja : pas de second tunnel." -ForegroundColor Yellow
} elseif (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "ngrok est introuvable dans le PATH : lancez-le a la main (voir la documentation)." -ForegroundColor Red
} else {
    # Même interpréteur que celui qui exécute ce script (powershell ou pwsh selon le poste)
    $interpreteur = (Get-Process -Id $PID).Path
    Start-Process $interpreteur -ArgumentList "-NoExit", "-Command",
        "ngrok http $Port --url https://$DomaineNgrok"
}

python -m app.taches serveur --port $Port
