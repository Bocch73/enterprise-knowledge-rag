$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
$prettierPath = Join-Path $projectRoot "frontend\node_modules\.bin\prettier.cmd"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Backend virtual environment was not found: $pythonPath"
}
if (-not (Test-Path -LiteralPath $prettierPath -PathType Leaf)) {
    throw "Frontend dependencies were not found. Run npm ci in frontend first."
}

Push-Location $backendRoot
try {
    & $pythonPath -m pytest tests/test_config.py tests/test_worker_cli.py `
        tests/test_deployment_assets.py -q
    if ($LASTEXITCODE -ne 0) {
        throw "Deployment contract tests failed."
    }
}
finally {
    Pop-Location
}

$yamlFiles = @(
    (Join-Path $projectRoot ".github\workflows\quality-gates.yml"),
    (Join-Path $projectRoot ".github\workflows\ci.yml"),
    (Join-Path $projectRoot ".github\workflows\release.yml"),
    (Join-Path $projectRoot ".github\dependabot.yml"),
    (Join-Path $projectRoot "deploy\compose.production.yml")
)

& $prettierPath --check @yamlFiles
if ($LASTEXITCODE -ne 0) {
    throw "Deployment YAML formatting or syntax check failed."
}

Write-Host "Deployment static verification passed. Docker was not required." -ForegroundColor Green
