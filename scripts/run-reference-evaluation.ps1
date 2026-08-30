param(
    [ValidateSet("retrieval", "full")]
    [string]$Mode = "retrieval",

    [ValidateSet("deterministic", "configured")]
    [string]$GenerationProvider = "deterministic",

    [ValidateSet("deterministic", "configured")]
    [string]$EmbeddingProvider = "deterministic",

    [ValidateSet("deterministic", "configured")]
    [string]$RerankProvider = "deterministic",

    [string]$Output,

    [switch]$AllowThresholdFailure
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot "backend"
$Python = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Backend virtual environment is missing: $Python"
}

if (-not $Output) {
    $Output = Join-Path $ProjectRoot "evaluation\reports\reference-$Mode-latest.json"
}
elseif (-not [System.IO.Path]::IsPathRooted($Output)) {
    $Output = Join-Path $ProjectRoot $Output
}

$Arguments = @(
    "-m", "app.cli.run_reference_evaluation",
    "--mode", $Mode,
    "--embedding-provider", $EmbeddingProvider,
    "--rerank-provider", $RerankProvider,
    "--generation-provider", $GenerationProvider,
    "--output", $Output
)
if ($AllowThresholdFailure) {
    $Arguments += "--allow-threshold-failure"
}

Push-Location $BackendRoot
try {
    & $Python @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
