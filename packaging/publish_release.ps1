param(
    [string]$Version = "3.1"
)

# Pushes main + the version tag and creates the GitHub release with the
# installer attached. Requires an authenticated GitHub CLI: run `gh auth login`
# first. Build the installer beforehand with build_app.ps1 then build_installer.ps1.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$tag = "v$Version"
$notes = Join-Path $root "RELEASE_NOTES_v$Version.md"
$setupExe = Join-Path $root "release\OctoBrowse-$Version-Setup.exe"

gh auth status | Out-Null

git -C $root push origin main
git -C $root push origin $tag

$assets = @()
if (Test-Path -LiteralPath $setupExe) { $assets += $setupExe }

$ghArgs = @("release", "create", $tag, "--title", "OctoBrowse $Version", "--notes-file", $notes)
$ghArgs += $assets
& gh @ghArgs

Write-Host "Release $tag published." -ForegroundColor Green
if (-not $assets) {
    Write-Host "No installer found at $setupExe - build it and run: gh release upload $tag `"$setupExe`"" -ForegroundColor Yellow
}
