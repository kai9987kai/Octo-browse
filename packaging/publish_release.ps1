param(
    [string]$Version = "",
    [string]$Python = ""
)

# Publish an already-built, verified release. This script never creates a
# release without all expected artifacts and stops on every git/gh failure.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "build_common.ps1")

$Python = Resolve-OctoPython -Root $root -Python $Python
$Version = Get-OctoVersion -Root $root -Python $Python -RequestedVersion $Version
$tag = "v$Version"
$notes = Join-Path $root "RELEASE_NOTES_v$Version.md"
$releaseDir = Join-Path $root "release"
$assets = @(
    (Join-Path $releaseDir "OctoBrowse-$Version.exe"),
    (Join-Path $releaseDir "OctoBrowse-$Version-Setup.exe"),
    (Join-Path $releaseDir "SHA256SUMS.txt"),
    (Join-Path $releaseDir "build-manifest.json")
)

if (-not (Test-Path -LiteralPath $notes -PathType Leaf)) {
    throw "Release notes not found: $notes"
}
foreach ($asset in $assets) {
    if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) {
        throw "Required release artifact not found: $asset"
    }
}

& gh auth status
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI authentication failed." }
$status = & git -C $root status --porcelain --untracked-files=normal
if ($LASTEXITCODE -ne 0) { throw "Could not inspect git working-tree status." }
if ($status) { throw "Working tree is not clean; commit all release sources before publishing." }
& git -C $root rev-parse --verify "refs/tags/$tag"
if ($LASTEXITCODE -ne 0) { throw "Local release tag does not exist: $tag" }

& git -C $root push origin main
if ($LASTEXITCODE -ne 0) { throw "Pushing main failed." }
& git -C $root push origin $tag
if ($LASTEXITCODE -ne 0) { throw "Pushing $tag failed." }

$ghArguments = @(
    "release", "create", $tag,
    "--title", "OctoBrowse $Version",
    "--notes-file", $notes
) + $assets
& gh @ghArguments
if ($LASTEXITCODE -ne 0) { throw "Creating GitHub release $tag failed." }

Write-Host "Release $tag published with $($assets.Count) verified assets." -ForegroundColor Green
