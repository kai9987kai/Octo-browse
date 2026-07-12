param(
    [string]$Python = "",
    [string]$Version = "",
    [switch]$SkipDependencyInstall
)

# Build a genuinely standalone, single-file Windows executable. The installer
# uses the faster onedir build; this artifact is for portable use.

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

$releaseDir = Join-Path $root "release"
$outputExe = Join-Path $releaseDir "OctoBrowse-$Version.exe"
$workPath = Join-Path $root "build\pyinstaller-onefile"
$specPath = Join-Path $root "build\pyinstaller-portable-spec"
$versionFile = Join-Path $root "build\version_info.txt"
Remove-OctoBuildPath -Root $root -Path $outputExe
Remove-OctoBuildPath -Root $root -Path $workPath
Remove-OctoBuildPath -Root $root -Path $specPath
Write-OctoVersionFile -Version $Version -Path $versionFile
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
New-Item -ItemType Directory -Path $specPath -Force | Out-Null

$arguments = @(
    "-m", "PyInstaller"
) + (Get-OctoPyInstallerArguments -Root $root -VersionFile $versionFile) + @(
    "--onefile",
    "--name", "OctoBrowse-$Version",
    "--distpath", $releaseDir,
    "--workpath", $workPath,
    "--specpath", $specPath,
    (Join-Path $root "main.py")
)

$buildStarted = Get-Date
Push-Location $root
try {
    Invoke-OctoPython -Python $Python -Arguments $arguments -Description "PyInstaller onefile build"
}
finally {
    Pop-Location
}

$item = Assert-OctoExecutableMetadata -Path $outputExe -Version $Version
if ($item.LastWriteTime -lt $buildStarted) {
    throw "Portable executable timestamp predates this build; refusing a stale artifact."
}

[pscustomobject]@{
    Version = $Version
    Architecture = $architecture
    Executable = $item.FullName
    FileVersion = $item.VersionInfo.FileVersion
    ProductVersion = $item.VersionInfo.ProductVersion
    SizeMB = [math]::Round($item.Length / 1MB, 1)
    SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash
}
