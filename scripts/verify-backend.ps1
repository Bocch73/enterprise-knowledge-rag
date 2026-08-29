$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend virtual environment was not found: $pythonPath"
}

function Invoke-Check {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host "`n[$Name]"
    & $pythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Push-Location $backendRoot
try {
    Invoke-Check "Tests and coverage" @(
        "-m", "pytest", "--cov=app", "--cov-report=term-missing", "--cov-report=xml"
    )
    Invoke-Check "Migration drift check" @("-m", "alembic", "check")
    Invoke-Check "Lint check" @("-m", "ruff", "check", ".")
    Invoke-Check "Format check" @("-m", "ruff", "format", "--check", ".")
    Invoke-Check "Static type check" @("-m", "mypy", "app", "tests")
}
finally {
    Pop-Location
}

Write-Host "`nBackend verification passed."
