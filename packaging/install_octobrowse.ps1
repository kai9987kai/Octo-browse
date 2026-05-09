$ErrorActionPreference = "Stop"

$payloadDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadZip = Join-Path $payloadDir "OctoBrowse.zip"
if (-not (Test-Path -LiteralPath $payloadZip)) {
    throw "Installer payload not found: $payloadZip"
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\OctoBrowse"
$exePath = Join-Path $installDir "OctoBrowse.exe"

Stop-Process -Name "OctoBrowse" -Force -ErrorAction SilentlyContinue

try {
    if (Test-Path -LiteralPath $installDir) {
        Remove-Item -LiteralPath $installDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Expand-Archive -LiteralPath $payloadZip -DestinationPath $installDir -Force

    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath("Desktop")
    $startMenu = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\OctoBrowse"
    New-Item -ItemType Directory -Path $startMenu -Force | Out-Null

    foreach ($shortcutPath in @(
        (Join-Path $desktop "OctoBrowse.lnk"),
        (Join-Path $startMenu "OctoBrowse.lnk")
    )) {
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $exePath
        $shortcut.WorkingDirectory = $installDir
        $shortcut.IconLocation = $exePath
        $shortcut.Description = "Octo Browser"
        $shortcut.Save()
    }

    $uninstallPs1 = Join-Path $installDir "Uninstall-OctoBrowse.ps1"
    @'
$ErrorActionPreference = "SilentlyContinue"
Stop-Process -Name "OctoBrowse" -Force
$installDir = Join-Path $env:LOCALAPPDATA "Programs\OctoBrowse"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "OctoBrowse.lnk"
$startMenuDir = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\OctoBrowse"
Remove-Item -LiteralPath $desktopShortcut -Force
Remove-Item -LiteralPath $startMenuDir -Recurse -Force
Start-Process -FilePath "cmd.exe" -WindowStyle Hidden -ArgumentList "/c timeout /t 2 /nobreak >nul & rmdir /s /q `"$installDir`""
'@ | Set-Content -LiteralPath $uninstallPs1 -Encoding UTF8

    $uninstallCmd = Join-Path $installDir "Uninstall-OctoBrowse.cmd"
    '@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall-OctoBrowse.ps1"
' | Set-Content -LiteralPath $uninstallCmd -Encoding ASCII

    $unShortcut = $shell.CreateShortcut((Join-Path $startMenu "Uninstall OctoBrowse.lnk"))
    $unShortcut.TargetPath = $uninstallCmd
    $unShortcut.WorkingDirectory = $installDir
    $unShortcut.Description = "Uninstall OctoBrowse"
    $unShortcut.Save()

    Start-Process -FilePath $exePath -WorkingDirectory $installDir
}
finally {
    Write-Output "OctoBrowse install step finished."
}
