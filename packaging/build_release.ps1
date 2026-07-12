param(
    [string]$Python = "",
    [string]$Version = "",
    [switch]$SkipDependencyInstall,
    [switch]$SkipSmokeTests
)

# One-command release build: verify sources, build onedir + standalone EXE,
# create the Inno installer, smoke-test, and write checksums/manifest.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "build_common.ps1")

$Python = Resolve-OctoPython -Root $root -Python $Python
$Version = Get-OctoVersion -Root $root -Python $Python -RequestedVersion $Version

Push-Location $root
try {
    Invoke-OctoPython -Python $Python -Arguments @(
        "-m", "compileall", "-q", "main.py", "alpha.py", "octobrowse", "tests"
    ) -Description "Source compilation"
    Invoke-OctoPython -Python $Python -Arguments @(
        "-m", "unittest", "discover", "-s", "tests", "-v"
    ) -Description "Regression tests"
}
finally {
    Pop-Location
}

$buildAppArgs = @{
    Python = $Python
    Version = $Version
    SkipDependencyInstall = $SkipDependencyInstall
}
& (Join-Path $PSScriptRoot "build_app.ps1") @buildAppArgs
& (Join-Path $PSScriptRoot "build_portable.ps1") `
    -Python $Python -Version $Version -SkipDependencyInstall
& (Join-Path $PSScriptRoot "build_inno.ps1") -Python $Python -Version $Version
& (Join-Path $PSScriptRoot "verify_release.ps1") `
    -Python $Python -Version $Version -SkipSmokeTests:$SkipSmokeTests
