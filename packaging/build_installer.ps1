param(
    [string]$Version = "3.1"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$distDir = Join-Path $root "dist\OctoBrowse"
$releaseDir = Join-Path $root "release"
$payloadDir = Join-Path $releaseDir "installer_payload"
$payloadZip = Join-Path $payloadDir "OctoBrowse.zip"
$setupExe = Join-Path $releaseDir "OctoBrowse-$Version-Setup.exe"
$sedPath = Join-Path $releaseDir "OctoBrowse-$Version-iexpress.sed"

if (-not (Test-Path -LiteralPath (Join-Path $distDir "OctoBrowse.exe"))) {
    throw "Frozen app not found. Build dist\OctoBrowse first."
}

Remove-Item -LiteralPath $payloadDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
Remove-Item -LiteralPath $payloadZip, $setupExe, $sedPath -Force -ErrorAction SilentlyContinue

Compress-Archive -Path (Join-Path $distDir "*") -DestinationPath $payloadZip -CompressionLevel Optimal -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "install_octobrowse.ps1") -Destination $payloadDir -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "install_octobrowse.cmd") -Destination $payloadDir -Force

$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=OctoBrowse has been installed.
TargetName=$setupExe
FriendlyName=OctoBrowse $Version Installer
AppLaunched=install_octobrowse.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=install_octobrowse.cmd
UserQuietInstCmd=install_octobrowse.cmd
SourceFiles=SourceFiles

[SourceFiles]
SourceFiles0=$payloadDir

[SourceFiles0]
OctoBrowse.zip=
install_octobrowse.ps1=
install_octobrowse.cmd=
"@

$sed | Set-Content -LiteralPath $sedPath -Encoding ASCII

& "$env:WINDIR\System32\iexpress.exe" /N /Q $sedPath
Start-Sleep -Seconds 2
Wait-Process -Name "iexpress", "makecab" -Timeout 600 -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $setupExe)) {
    throw "IExpress did not produce $setupExe"
}

Remove-Item -LiteralPath $payloadDir -Recurse -Force -ErrorAction SilentlyContinue

Get-Item -LiteralPath $setupExe |
    Select-Object FullName, Length, LastWriteTime
