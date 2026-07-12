param(
    [string]$Version = "",
    [string]$Python = ""
)

# Build the primary per-user Windows installer from the verified onedir app.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "build_common.ps1")

$Python = Resolve-OctoPython -Root $root -Python $Python
$Version = Get-OctoVersion -Root $root -Python $Python -RequestedVersion $Version
$exe = Join-Path $root "dist\OctoBrowse\OctoBrowse.exe"
$null = Assert-OctoExecutableMetadata -Path $exe -Version $Version

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$iscc = $isccCandidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
    Select-Object -First 1
if (-not $iscc) {
    $command = Get-Command iscc -ErrorAction SilentlyContinue
    if ($command) { $iscc = $command.Source }
}
if (-not $iscc) {
    throw "Inno Setup (ISCC.exe) not found. Install it with: winget install --id JRSoftware.InnoSetup"
}

$releaseDir = Join-Path $root "release"
$setup = Join-Path $releaseDir "OctoBrowse-$Version-Setup.exe"
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
Remove-OctoBuildPath -Root $root -Path $setup

$iss = Join-Path $PSScriptRoot "octobrowse.iss"
$buildStarted = Get-Date
& $iscc "/Qp" "/DMyAppVersion=$Version" $iss
if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    throw "Inno Setup did not produce $setup"
}
$item = Get-Item -LiteralPath $setup
if ($item.LastWriteTime -lt $buildStarted) {
    throw "Installer timestamp predates this build; refusing a stale artifact."
}
if (-not $item.VersionInfo.ProductVersion.StartsWith($Version)) {
    throw "Installer ProductVersion '$($item.VersionInfo.ProductVersion)' does not match $Version."
}

[pscustomobject]@{
    Version = $Version
    Installer = $item.FullName
    FileVersion = $item.VersionInfo.FileVersion
    ProductVersion = $item.VersionInfo.ProductVersion
    SizeMB = [math]::Round($item.Length / 1MB, 1)
    SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash
}
