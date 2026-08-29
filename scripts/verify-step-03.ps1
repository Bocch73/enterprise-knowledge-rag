[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

$requiredFiles = @(
    'docs\requirements\functional-requirements.md',
    'docs\requirements\non-functional-requirements.md',
    'docs\requirements\acceptance-scenarios.md',
    'docs\requirements\traceability-matrix.md',
    'docs\architecture\system-architecture.md',
    'docs\architecture\technology-stack.md',
    'docs\architecture\decisions\README.md',
    'docs\architecture\decisions\0001-modular-monolith.md',
    'docs\architecture\decisions\0002-postgresql-pgvector.md',
    'docs\architecture\decisions\0003-hybrid-retrieval.md',
    'docs\architecture\decisions\0004-model-provider-abstraction.md',
    'docs\architecture\decisions\0005-asynchronous-ingestion.md',
    'docs\steps\03-requirements-and-architecture-summary.md',
    'docs\interview\03-requirements-and-architecture.md'
)

$missingFiles = @()
foreach ($relativePath in $requiredFiles) {
    $absolutePath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $absolutePath)) {
        $missingFiles += $relativePath
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host '[FAIL] Missing step-3 files:'
    $missingFiles | ForEach-Object { Write-Host ("  - {0}" -f $_) }
    exit 1
}
Write-Host ("[PASS] Required files: {0}" -f $requiredFiles.Count)

$functionalPath = Join-Path $projectRoot 'docs\requirements\functional-requirements.md'
$functionalText = Get-Content -Raw -LiteralPath $functionalPath
$functionalIds = [regex]::Matches($functionalText, 'FR-[A-Z]+-\d{3}') | ForEach-Object { $_.Value }
$duplicateFunctionalIds = $functionalIds | Group-Object | Where-Object Count -gt 1
if ($duplicateFunctionalIds) {
    Write-Host '[FAIL] Duplicate functional requirement identifiers:'
    $duplicateFunctionalIds | ForEach-Object { Write-Host ("  - {0}" -f $_.Name) }
    exit 1
}
Write-Host ("[PASS] Unique functional requirements: {0}" -f $functionalIds.Count)

$nonFunctionalPath = Join-Path $projectRoot 'docs\requirements\non-functional-requirements.md'
$nonFunctionalText = Get-Content -Raw -LiteralPath $nonFunctionalPath
$nonFunctionalIds = [regex]::Matches($nonFunctionalText, 'NFR-[A-Z]+-\d{3}') | ForEach-Object { $_.Value }
$duplicateNonFunctionalIds = $nonFunctionalIds | Group-Object | Where-Object Count -gt 1
if ($duplicateNonFunctionalIds) {
    Write-Host '[FAIL] Duplicate non-functional requirement identifiers:'
    $duplicateNonFunctionalIds | ForEach-Object { Write-Host ("  - {0}" -f $_.Name) }
    exit 1
}
Write-Host ("[PASS] Unique non-functional requirements: {0}" -f $nonFunctionalIds.Count)

$architecturePath = Join-Path $projectRoot 'docs\architecture\system-architecture.md'
$architectureText = Get-Content -Raw -LiteralPath $architecturePath
$mermaidBlocks = [regex]::Matches($architectureText, '```mermaid').Count
if ($mermaidBlocks -lt 4) {
    Write-Host ("[FAIL] Expected at least 4 architecture diagrams, found {0}" -f $mermaidBlocks)
    exit 1
}
Write-Host ("[PASS] Mermaid architecture diagrams: {0}" -f $mermaidBlocks)

Write-Host 'Step 3 verification completed.'
