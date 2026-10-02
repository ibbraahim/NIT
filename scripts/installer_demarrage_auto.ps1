# Lance Workly (serveur + ngrok) automatiquement à l'ouverture de session Windows, et empêche la
# mise en veille sur secteur. À exécuter UNE FOIS :
#
#   powershell -ExecutionPolicy Bypass -File scripts\installer_demarrage_auto.ps1
#
# Pour supprimer : Unregister-ScheduledTask -TaskName "Workly serveur" -Confirm:$false
$script = Join-Path $PSScriptRoot "demarrer_workly.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$declencheur = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$reglages = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
Register-ScheduledTask -TaskName "Workly serveur" -Action $action -Trigger $declencheur `
    -Settings $reglages -Force | Out-Null
powercfg /change standby-timeout-ac 0
Write-Host "Demarrage automatique installe : Workly se lancera a l'ouverture de session." -ForegroundColor Green
Write-Host "Mise en veille sur secteur desactivee."
