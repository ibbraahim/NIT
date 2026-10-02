# Enregistre UNE FOIS les réglages d'alerte e-mail de Workly (variables d'environnement de
# l'utilisateur Windows). Le code d'application Gmail est saisi à l'écran, sans être affiché.
#
#   powershell -ExecutionPolicy Bypass -File scripts\configurer_alertes.ps1
#
# Option : -Destinataire autre@exemple.com pour recevoir les alertes ailleurs que sur le compte
# d'envoi. Le port 465 (SSL direct) est celui qui fonctionne quand 587 est bloqué.
param(
    [string]$Compte = "myworkly2026@gmail.com",
    [string]$Destinataire = "",
    [int]$Port = 465
)

if (-not $Destinataire) { $Destinataire = $Compte }
$saisie = Read-Host "Code d'application Gmail (16 caracteres)" -AsSecureString
$motDePasse = ([Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($saisie))).Replace(" ", "")
if ($motDePasse.Length -lt 8) {
    Write-Host "Code trop court : rien n'a ete enregistre." -ForegroundColor Red
    exit 1
}

[Environment]::SetEnvironmentVariable("WORKLY_SMTP_UTILISATEUR", $Compte, "User")
[Environment]::SetEnvironmentVariable("WORKLY_SMTP_MOT_DE_PASSE", $motDePasse, "User")
[Environment]::SetEnvironmentVariable("WORKLY_ALERTE_DESTINATAIRE", $Destinataire, "User")
[Environment]::SetEnvironmentVariable("WORKLY_SMTP_PORT", "$Port", "User")
Write-Host "Reglages d'alerte enregistres pour $Compte -> $Destinataire (port $Port)." -ForegroundColor Green
Write-Host "Ils seront pris en compte au prochain demarrage de Workly."
