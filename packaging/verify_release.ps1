param(
    [string]$Version = "",
    [string]$Python = "",
    [switch]$SkipSmokeTests
)

# Validate both frozen application formats and the installer, then emit
# deterministic checksums and a machine-readable release manifest.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "build_common.ps1")

$Python = Resolve-OctoPython -Root $root -Python $Python
$Version = Get-OctoVersion -Root $root -Python $Python -RequestedVersion $Version
$architecture = Assert-OctoX64Python -Python $Python
$releaseDir = Join-Path $root "release"
$onedirRoot = Join-Path $root "dist\OctoBrowse"
$onedirExe = Join-Path $onedirRoot "OctoBrowse.exe"
$portableExe = Join-Path $releaseDir "OctoBrowse-$Version.exe"
$installerExe = Join-Path $releaseDir "OctoBrowse-$Version-Setup.exe"

$onedirItem = Assert-OctoExecutableMetadata -Path $onedirExe -Version $Version
$portableItem = Assert-OctoExecutableMetadata -Path $portableExe -Version $Version
if (-not (Test-Path -LiteralPath $installerExe -PathType Leaf)) {
    throw "Installer not found: $installerExe"
}
$installerItem = Get-Item -LiteralPath $installerExe
if (-not $installerItem.VersionInfo.ProductVersion.StartsWith($Version)) {
    throw "Installer ProductVersion '$($installerItem.VersionInfo.ProductVersion)' does not match $Version."
}

foreach ($requiredName in @("QtWebEngineProcess.exe", "qtwebengine_resources.pak", "icudtl.dat", "qt.conf")) {
    if (-not (Get-ChildItem -LiteralPath $onedirRoot -Recurse -File -Filter $requiredName | Select-Object -First 1)) {
        throw "Required QtWebEngine runtime file is missing: $requiredName"
    }
}
foreach ($excludedName in @("cv2", "numpy", "pocketsphinx", "pocketsphinx-data")) {
    if (Get-ChildItem -LiteralPath $onedirRoot -Recurse -Force |
        Where-Object { $_.Name -eq $excludedName } |
        Select-Object -First 1) {
        throw "Excluded release payload '$excludedName' is still present."
    }
}
if (Get-ChildItem -LiteralPath $onedirRoot -Recurse -File |
    Where-Object { $_.Name -match '\.debug\.' } |
    Select-Object -First 1) {
    throw "Duplicate Qt debug resource packs are still present."
}

$archiveListing = & $Python -m PyInstaller.utils.cliutils.archive_viewer -r -b $onedirExe 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the frozen Python archive (exit $LASTEXITCODE)."
}
$portableListing = & $Python -m PyInstaller.utils.cliutils.archive_viewer -r -b $portableExe 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the standalone executable archive (exit $LASTEXITCODE)."
}
if (($portableListing -join "`n") -match '(?i)\.debug\.(pak|bin)') {
    throw "Standalone executable still contains duplicate Qt debug resource packs."
}
if (($portableListing -join "`n") -match '(?i)pocketsphinx-data') {
    throw "Standalone executable still contains unused PocketSphinx model data."
}
foreach ($module in @(
    "octobrowse.ai_context",
    "octobrowse.filtering",
    "octobrowse.session",
    "octobrowse.urls",
    "octobrowse.version",
    "octobrowse.workspaces"
)) {
    if (($archiveListing -join "`n") -notmatch [regex]::Escape($module)) {
        throw "Frozen archive is missing application module: $module"
    }
}

function Invoke-SmokeTest {
    param([Parameter(Mandatory = $true)][string]$Executable)

    $process = Start-Process -FilePath $Executable -ArgumentList "--smoke-test" `
        -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(90000)) {
        $process.Kill()
        throw "Smoke test timed out: $Executable"
    }
    if ($process.ExitCode -ne 0) {
        throw "Smoke test failed with exit code $($process.ExitCode): $Executable"
    }
}

if (-not $SkipSmokeTests) {
    Invoke-SmokeTest -Executable $onedirExe
    Invoke-SmokeTest -Executable $portableExe
}

$artifacts = @($portableItem, $installerItem)
$artifactRecords = @()
$checksumLines = @()
foreach ($artifact in $artifacts) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact.FullName).Hash
    $checksumLines += "$hash  $($artifact.Name)"
    $signature = Get-AuthenticodeSignature -LiteralPath $artifact.FullName
    $artifactRecords += [ordered]@{
        file = $artifact.Name
        bytes = $artifact.Length
        sha256 = $hash
        file_version = $artifact.VersionInfo.FileVersion
        product_version = $artifact.VersionInfo.ProductVersion
        authenticode = [string]$signature.Status
    }
}
$checksumsPath = Join-Path $releaseDir "SHA256SUMS.txt"
Set-Content -LiteralPath $checksumsPath -Value ($checksumLines -join "`n") -Encoding ASCII

$onedirFiles = Get-ChildItem -LiteralPath $onedirRoot -Recurse -File
$manifest = [ordered]@{
    product = "OctoBrowse"
    version = $Version
    target = "Windows x64"
    python = (& $Python --version 2>&1 | Out-String).Trim()
    architecture = $architecture
    generated_utc = [DateTime]::UtcNow.ToString("o")
    onedir = [ordered]@{
        files = $onedirFiles.Count
        bytes = ($onedirFiles | Measure-Object -Property Length -Sum).Sum
        executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $onedirExe).Hash
    }
    artifacts = $artifactRecords
    signed = @($artifactRecords | Where-Object { $_.authenticode -eq "Valid" }).Count -eq $artifactRecords.Count
}
$manifestPath = Join-Path $releaseDir "build-manifest.json"
Set-Content -LiteralPath $manifestPath -Value ($manifest | ConvertTo-Json -Depth 6) -Encoding UTF8

[pscustomobject]@{
    Version = $Version
    PortableEXE = $portableExe
    Installer = $installerExe
    Checksums = $checksumsPath
    Manifest = $manifestPath
    SmokeTests = if ($SkipSmokeTests) { "skipped" } else { "passed" }
    Signed = $manifest.signed
}
