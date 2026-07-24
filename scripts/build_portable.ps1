param(
    [switch]$SkipZip
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$specPath = Join-Path $projectRoot "he3signal_portable.spec"
$distRoot = Join-Path $projectRoot "dist"
$portableDir = Join-Path $distRoot "He3Signal"
$zipPath = Join-Path $distRoot "He3Signal-Win11-x64.zip"

Push-Location $projectRoot
try {
    conda run -n signal_create python -m PyInstaller --noconfirm --clean $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $portableDir "He3Signal.exe"))) {
        throw "Portable executable was not created."
    }
    Copy-Item -LiteralPath (Join-Path $projectRoot "PORTABLE_README.txt") -Destination $portableDir -Force

    if (-not $SkipZip) {
        if (Test-Path -LiteralPath $zipPath) {
            Remove-Item -LiteralPath $zipPath -Force
        }
        tar.exe -a -c -f $zipPath -C $distRoot "He3Signal"
        if ($LASTEXITCODE -ne 0) {
            throw "ZIP creation failed with exit code $LASTEXITCODE"
        }
        Write-Host "Portable ZIP: $zipPath"
    }

    Write-Host "Portable folder: $portableDir"
}
finally {
    Pop-Location
}
