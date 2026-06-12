param(
    [string]$Python = ""
)

# Freezes OctoBrowse into dist\OctoBrowse\OctoBrowse.exe with PyInstaller.
# QtWebEngine needs its resources/locales and QtWebEngineProcess.exe bundled,
# so we collect the whole PyQt6 package rather than relying on minimal imports.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $Python) {
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    $Python = if (Test-Path $venvPython) { $venvPython } else { "python" }
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $root "requirements.txt")
& $Python -m pip install pyinstaller

Push-Location $root
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --name OctoBrowse `
        --collect-all PyQt6 `
        (Join-Path $root "main.py")
}
finally {
    Pop-Location
}

$exe = Join-Path $root "dist\OctoBrowse\OctoBrowse.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "PyInstaller did not produce $exe"
}
Get-Item -LiteralPath $exe | Select-Object FullName, Length, LastWriteTime
