Set-StrictMode -Version Latest

function Resolve-OctoPython {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [string]$Python = ""
    )

    $candidate = $Python
    if (-not $candidate) {
        $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
        $candidate = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
    }
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Python executable not found: $candidate"
    }
    return $command.Source
}

function Invoke-OctoPython {
    param(
        [Parameter(Mandatory = $true)][string]$Python,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )

    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

function Get-OctoVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Python,
        [string]$RequestedVersion = ""
    )

    Push-Location $Root
    try {
        $output = & $Python -c "from octobrowse.version import __version__; print(__version__)"
        if ($LASTEXITCODE -ne 0) {
            throw "Could not read octobrowse.version with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
    $detected = ([string]($output | Select-Object -Last 1)).Trim()
    if ($detected -notmatch '^\d+\.\d+(?:\.\d+)?$') {
        throw "Application version '$detected' is not a supported numeric release version."
    }
    if ($RequestedVersion -and $RequestedVersion -ne $detected) {
        throw "Requested version $RequestedVersion does not match application version $detected."
    }
    return $detected
}

function Assert-OctoX64Python {
    param([Parameter(Mandatory = $true)][string]$Python)

    $architecture = & $Python -c "import struct, sysconfig; print('{}:{}'.format(sysconfig.get_platform(), struct.calcsize('P') * 8))"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not determine Python architecture."
    }
    $architecture = ([string]$architecture).Trim()
    if ($architecture -notin @("win-amd64:64", "win_amd64:64")) {
        throw "This release pipeline currently targets x64 Windows; Python reported $architecture."
    }
    return $architecture
}

function Remove-OctoBuildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $targetFull = [IO.Path]::GetFullPath($Path)
    if (-not $targetFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the repository: $targetFull"
    }
    if (Test-Path -LiteralPath $targetFull) {
        Remove-Item -LiteralPath $targetFull -Recurse -Force
    }
}

function Write-OctoVersionFile {
    param(
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $parts = @($Version.Split('.') | ForEach-Object { [int]$_ })
    while ($parts.Count -lt 4) { $parts += 0 }
    $tuple = ($parts[0..3] -join ', ')
    $versionString = ($parts[0..3] -join '.')
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $content = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($tuple),
    prodvers=($tuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'OctoBrowse'),
          StringStruct('FileDescription', 'OctoBrowse desktop web browser'),
          StringStruct('FileVersion', '$versionString'),
          StringStruct('InternalName', 'OctoBrowse'),
          StringStruct('LegalCopyright', 'Copyright (c) 2026 OctoBrowse contributors'),
          StringStruct('OriginalFilename', 'OctoBrowse.exe'),
          StringStruct('ProductName', 'OctoBrowse'),
          StringStruct('ProductVersion', '$versionString')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
    Set-Content -LiteralPath $Path -Value $content -Encoding UTF8
}

function Install-OctoBuildDependencies {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Python
    )

    Invoke-OctoPython -Python $Python -Arguments @(
        "-m", "pip", "install", "-r", (Join-Path $Root "requirements.txt"), "pyinstaller>=6.10"
    ) -Description "Build dependency installation"
}

function Get-OctoPyInstallerArguments {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$VersionFile
    )

    return @(
        "--noconfirm",
        "--clean",
        "--log-level", "WARN",
        "--windowed",
        "--noupx",
        "--icon", (Join-Path $Root "assets\octobrowse.ico"),
        "--version-file", $VersionFile,
        "--add-data", ((Join-Path $Root "assets") + ";assets"),
        "--additional-hooks-dir", (Join-Path $Root "packaging\hooks"),
        "--exclude-module", "cv2",
        "--exclude-module", "numpy",
        "--exclude-module", "pocketsphinx"
    )
}

function Assert-OctoExecutableMetadata {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Version
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Expected executable was not produced: $Path"
    }
    $item = Get-Item -LiteralPath $Path
    if (-not $item.VersionInfo.ProductVersion.StartsWith($Version)) {
        throw "Executable ProductVersion '$($item.VersionInfo.ProductVersion)' does not match $Version."
    }
    if ($item.Length -lt 1MB) {
        throw "Executable is unexpectedly small: $($item.Length) bytes."
    }
    return $item
}
