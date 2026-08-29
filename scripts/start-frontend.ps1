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
& $npmCommand run dev
