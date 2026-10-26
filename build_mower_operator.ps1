[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

$distRoot = Join-Path $projectRoot "dist"
$appDir = Join-Path $distRoot "MowerOperator"
$runtimeData = Join-Path $appDir "data"
$backupRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("MowerOperatorBuild_" + [guid]::NewGuid().ToString("N"))
$backupData = Join-Path $backupRoot "data"
$hadRuntimeData = Test-Path -LiteralPath $runtimeData
$buildSucceeded = $false

Write-Host "Mower Operator wird gebaut..." -ForegroundColor Cyan
Write-Host "Python: $python"

& $python -m PyInstaller --version | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller fehlt. Bitte zuerst ausfuehren: python -m pip install pyinstaller"
}

try {
    if ($hadRuntimeData) {
        New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
        Copy-Item -LiteralPath $runtimeData -Destination $backupData -Recurse -Force
        Write-Host "Vorhandener data-Ordner wurde temporaer gesichert."
    }

    Push-Location $projectRoot
    try {
        $arguments = @(
            "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onedir",
            "--name", "MowerOperator",
            "--paths", ".",
            "--collect-all", "customtkinter",
            "App\mower_operator_app.py"
        )
        & $python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller wurde mit Exit-Code $LASTEXITCODE beendet."
        }
    }
    finally {
        Pop-Location
    }

    if ($hadRuntimeData) {
        Copy-Item -LiteralPath $backupData -Destination $appDir -Recurse -Force
        Write-Host "Vorhandener data-Ordner wurde wiederhergestellt."
    }
    else {
        $directories = @(
            "config",
            "tracker",
            "messungen\kalibrierung",
            "messungen\messplaene",
            "projekte",
            "logs"
        )
        foreach ($relativePath in $directories) {
            New-Item -ItemType Directory -Path (Join-Path $runtimeData $relativePath) -Force | Out-Null
        }

        $externalConfig = Join-Path $projectRoot "data\config\mower_config.json"
        $legacyConfig = Join-Path $projectRoot "config\mower_config.json"
        $targetConfig = Join-Path $runtimeData "config\mower_config.json"

        if (Test-Path -LiteralPath $externalConfig) {
            Copy-Item -LiteralPath $externalConfig -Destination $targetConfig -Force
        }
        elseif (Test-Path -LiteralPath $legacyConfig) {
            Copy-Item -LiteralPath $legacyConfig -Destination $targetConfig -Force
        }
        else {
            Write-Warning "Keine mower_config.json gefunden. Beim ersten Start wird eine Standarddatei erzeugt."
        }

        $trackerSource = Join-Path $projectRoot "data\tracker"
        $legacyTrackerFile = Join-Path $projectRoot "data\tracker_station.txt"
        $trackerTarget = Join-Path $runtimeData "tracker"

        if (Test-Path -LiteralPath $trackerSource) {
            Get-ChildItem -LiteralPath $trackerSource -Force | ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination $trackerTarget -Recurse -Force
            }
        }
        elseif (Test-Path -LiteralPath $legacyTrackerFile) {
            Copy-Item -LiteralPath $legacyTrackerFile -Destination (Join-Path $trackerTarget "tracker_station.txt") -Force
        }
    }

    $buildSucceeded = $true
}
catch {
    if ($hadRuntimeData -and (Test-Path -LiteralPath $backupData)) {
        New-Item -ItemType Directory -Path $appDir -Force | Out-Null
        Copy-Item -LiteralPath $backupData -Destination $appDir -Recurse -Force
        Write-Warning "Der bisherige data-Ordner wurde nach dem Buildfehler wiederhergestellt."
    }
    throw
}
finally {
    if ($buildSucceeded -and (Test-Path -LiteralPath $backupRoot)) {
        Remove-Item -LiteralPath $backupRoot -Recurse -Force
    }
    elseif (Test-Path -LiteralPath $backupRoot) {
        Write-Warning "Sicherheitskopie verbleibt unter: $backupRoot"
    }
}

Write-Host ""
Write-Host "Build erfolgreich." -ForegroundColor Green
Write-Host "EXE:  $(Join-Path $appDir 'MowerOperator.exe')"
Write-Host "Daten: $runtimeData"
