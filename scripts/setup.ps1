$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3.12 -m venv .venv }
    & '.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    & "$PSScriptRoot\prepare-tools.ps1"
} finally { Pop-Location }
