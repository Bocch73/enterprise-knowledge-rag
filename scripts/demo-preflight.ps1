$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$nodeItem = Get-ChildItem -LiteralPath (Join-Path $projectRoot ".tools") -Filter "node.exe" -File -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -eq $nodeItem) {
    throw "Project-local Node.js was not found under .tools."
}
$nodePath = $nodeItem.FullName
$fixtureRoot = Join-Path $projectRoot "evaluation\fixtures"
$reportRoot = Join-Path $projectRoot "evaluation\reports"

$requiredFiles = @(
    $pythonPath,
    $nodePath,
    (Join-Path $fixtureRoot "leave-policy.md"),
    (Join-Path $fixtureRoot "security-policy.md"),
    (Join-Path $fixtureRoot "travel-policy.md"),
    (Join-Path $reportRoot "reference-deterministic-full-v1.json"),
    (Join-Path $reportRoot "reference-deepseek-v1.json"),
    (Join-Path $projectRoot "docs\delivery\demo-script.md")
)

$missing = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($missing.Count -gt 0) {
    throw "Demo preflight failed. Missing $($missing.Count) required file(s):`n$($missing -join "`n")"
}

$ignoredSecretPaths = @(
    "backend/.env",
    "backend/.env.deepseek",
    "deploy/secrets/postgres_admin_password",
    "deploy/secrets/database_password",
    "deploy/secrets/app_secret_key",
    "deploy/secrets/metrics_token"
)

foreach ($secretPath in $ignoredSecretPaths) {
    & git -c "safe.directory=$projectRoot" -C $projectRoot check-ignore --quiet -- $secretPath
    if ($LASTEXITCODE -ne 0) {
        throw "Secret path is not ignored by Git: $secretPath"
    }
}

& $pythonPath --version
if ($LASTEXITCODE -ne 0) {
    throw "Project Python could not run."
}
& $nodePath --version
if ($LASTEXITCODE -ne 0) {
    throw "Project Node.js could not run."
}

Write-Host "Demo preflight passed. No service was started and no external model was called." -ForegroundColor Green
