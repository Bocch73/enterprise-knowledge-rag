param(
    [switch]$EndToEnd
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "frontend"
$nodeDirectory = Join-Path $projectRoot ".tools\node-v24.19.0-win-x64"
$npmCommand = Join-Path $nodeDirectory "npm.cmd"

if (-not (Test-Path -LiteralPath $npmCommand -PathType Leaf)) {
    throw "Local Node.js was not found. Expected: $npmCommand"
}

$env:Path = "$nodeDirectory;$env:Path"
Set-Location -LiteralPath $frontendRoot

$commands = @("format:check", "lint", "type-check", "test:coverage", "build")
foreach ($command in $commands) {
    & $npmCommand run $command
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend verification failed at npm run $command"
    }
}

if ($EndToEnd) {
    & $npmCommand run test:e2e
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend end-to-end verification failed"
    }
}

Write-Host "Frontend verification passed." -ForegroundColor Green
