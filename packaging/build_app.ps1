param(
    [string]$Python = "",
    [string]$Version = "",
    [switch]$SkipDependencyInstall
)

# Build the onedir application consumed by the Inno Setup installer.
# Native command failures, stale output, architecture drift, missing
# QtWebEngine resources, and version mismatches all fail the build.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "build_common.ps1")

$Python = Resolve-OctoPython -Root $root -Python $Python
$Version = Get-OctoVersion -Root $root -Python $Python -RequestedVersion $Version
$architecture = Assert-OctoX64Python -Python $Python

if (-not $SkipDependencyInstall) {
    Install-OctoBuildDependencies -Root $root -Python $Python
}

$distApp = Join-Path $root "dist\OctoBrowse"
$workPath = Join-Path $root "build\pyinstaller-onedir"
$specPath = Join-Path $root "build\pyinstaller-spec"
$versionFile = Join-Path $root "build\version_info.txt"
Remove-OctoBuildPath -Root $root -Path $distApp
Remove-OctoBuildPath -Root $root -Path $workPath
Remove-OctoBuildPath -Root $root -Path $specPath
Write-OctoVersionFile -Version $Version -Path $versionFile
New-Item -ItemType Directory -Path $specPath -Force | Out-Null

$arguments = @(
    "-m", "PyInstaller"
) + (Get-OctoPyInstallerArguments -Root $root -VersionFile $versionFile) + @(
    "--onedir",
    "--name", "OctoBrowse",
    "--distpath", (Join-Path $root "dist"),
    "--workpath", $workPath,
    "--specpath", $specPath,
    (Join-Path $root "main.py")
)

$buildStarted = Get-Date
Push-Location $root
try {
    Invoke-OctoPython -Python $Python -Arguments $arguments -Description "PyInstaller onedir build"
}
finally {
    Pop-Location
}

$exe = Join-Path $distApp "OctoBrowse.exe"
$item = Assert-OctoExecutableMetadata -Path $exe -Version $Version
if ($item.LastWriteTime -lt $buildStarted) {
    throw "Executable timestamp predates this build; refusing a stale artifact."
}

foreach ($requiredName in @("QtWebEngineProcess.exe", "qtwebengine_resources.pak", "icudtl.dat", "qt.conf")) {
    $match = Get-ChildItem -LiteralPath $distApp -Recurse -File -Filter $requiredName |
        Select-Object -First 1
    if (-not $match) {
        throw "Required QtWebEngine runtime file is missing: $requiredName"
    }
}
$sampleManifest = Get-ChildItem -LiteralPath $distApp -Recurse -File -Filter "manifest.json" |
    Where-Object { $_.FullName -like "*examples\mv3_hello\manifest.json" } |
    Select-Object -First 1
if (-not $sampleManifest) {
    throw "Bundled MV3 inspector sample is missing: examples\mv3_hello\manifest.json"
}

$files = Get-ChildItem -LiteralPath $distApp -Recurse -File
$size = ($files | Measure-Object -Property Length -Sum).Sum
[pscustomobject]@{
    Version = $Version
    Architecture = $architecture
    Executable = $item.FullName
    FileVersion = $item.VersionInfo.FileVersion
    ProductVersion = $item.VersionInfo.ProductVersion
    Files = $files.Count
    SizeMB = [math]::Round($size / 1MB, 1)
    SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash
}
