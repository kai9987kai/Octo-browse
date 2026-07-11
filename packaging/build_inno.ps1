param(
    [string]$Version = "3.2"
)

# Builds release\OctoBrowse-<Version>-Setup.exe with Inno Setup from the
# PyInstaller onedir output (run build_app.ps1 first). This is the preferred
# installer: it has a real uninstaller, shortcuts, and an Add/Remove entry.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$exe = Join-Path $root "dist\OctoBrowse\OctoBrowse.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Frozen app not found at $exe. Run packaging\build_app.ps1 first."
}

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$iscc = $isccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $iscc) {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) {
    throw "Inno Setup (ISCC.exe) not found. Install it with: winget install --id JRSoftware.InnoSetup"
}

$iss = Join-Path $PSScriptRoot "octobrowse.iss"
& $iscc "/DMyAppVersion=$Version" $iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

$setup = Join-Path $root "release\OctoBrowse-$Version-Setup.exe"
if (-not (Test-Path -LiteralPath $setup)) { throw "Inno Setup did not produce $setup" }
Get-Item -LiteralPath $setup | Select-Object FullName, Length, LastWriteTime
