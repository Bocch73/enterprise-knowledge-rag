param(
    [switch]$FullBackend
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$Python = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Backend virtual environment is missing: $Python"
}

Push-Location $BackendRoot
try {
    & $Python -m app.cli.evaluate_rag --validate-only
    if ($LASTEXITCODE -ne 0) { throw "Evaluation dataset validation failed." }

    & $Python -m pytest tests/test_evaluation.py -q
    if ($LASTEXITCODE -ne 0) { throw "Evaluation tests failed." }

    & $Python -m ruff check app/modules/evaluation app/cli/evaluate_rag.py app/cli/run_reference_evaluation.py tests/test_evaluation.py
    if ($LASTEXITCODE -ne 0) { throw "Evaluation lint failed." }

    & $Python -m mypy app/modules/evaluation app/cli/evaluate_rag.py app/cli/run_reference_evaluation.py tests/test_evaluation.py
    if ($LASTEXITCODE -ne 0) { throw "Evaluation type check failed." }
}
finally {
    Pop-Location
}

if ($FullBackend) {
    & (Join-Path $PSScriptRoot "verify-backend.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Full backend verification failed." }
}

Write-Host "Evaluation quality checks passed."
