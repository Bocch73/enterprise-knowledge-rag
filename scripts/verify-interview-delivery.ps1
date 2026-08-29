$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$requiredRelativeFiles = @(
    "docs/14-interview-delivery.md",
    "docs/steps/14-interview-delivery-summary.md",
    "docs/delivery/README.md",
    "docs/delivery/demo-script.md",
    "docs/delivery/resume-and-introduction.md",
    "docs/delivery/architecture-defense.md",
    "docs/delivery/final-delivery-checklist.md",
    "docs/interview/README.md",
    "docs/interview/14-project-defense.md",
    "evaluation/reports/reference-deterministic-full-v1.json",
    "evaluation/reports/reference-deepseek-v1.json"
)

$missing = @(
    $requiredRelativeFiles | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $projectRoot $_) -PathType Leaf)
    }
)
if ($missing.Count -gt 0) {
    throw "Interview delivery is incomplete. Missing: $($missing -join ', ')"
}

$markdownFiles = Get-ChildItem -LiteralPath $projectRoot -Filter "*.md" -File -Recurse |
    Where-Object {
        $_.FullName -notmatch '[\\/](\.venv|node_modules|\.tools)[\\/]'
    }
$linkPattern = '\[[^\]]+\]\((?<target>[^)]+)\)'
$brokenLinks = [System.Collections.Generic.List[string]]::new()

foreach ($markdownFile in $markdownFiles) {
    $content = Get-Content -LiteralPath $markdownFile.FullName -Raw
    foreach ($match in [regex]::Matches($content, $linkPattern)) {
        $target = $match.Groups['target'].Value.Trim().Trim('<', '>')
        if ($target -match '^(https?://|mailto:|#)' -or [string]::IsNullOrWhiteSpace($target)) {
            continue
        }
        $pathOnly = ($target -split '#', 2)[0]
        $pathOnly = [System.Uri]::UnescapeDataString($pathOnly)
        $resolved = Join-Path $markdownFile.DirectoryName $pathOnly
        if (-not (Test-Path -LiteralPath $resolved)) {
            $relativeMarkdown = [System.IO.Path]::GetRelativePath($projectRoot, $markdownFile.FullName)
            $brokenLinks.Add("$relativeMarkdown -> $target")
        }
    }
}

if ($brokenLinks.Count -gt 0) {
    throw "Broken local Markdown link(s):`n$($brokenLinks -join "`n")"
}

$forbiddenTrackedPatterns = @(
    '(^|/)\.env($|\.)',
    '(^|/)\.venv/',
    '(^|/)node_modules/',
    '(^|/)\.tools/',
    '^deploy/secrets/[^.].*',
    '^deploy/backups/'
)
$prospectiveFiles = @(& git -c "safe.directory=$projectRoot" -C $projectRoot ls-files --cached --others --exclude-standard)
if ($LASTEXITCODE -ne 0) {
    throw "Could not list prospective Git files."
}

$forbidden = @(
    $prospectiveFiles | Where-Object {
        $candidate = $_
        if ($candidate -match '\.example$') {
            return $false
        }
        $forbiddenTrackedPatterns | Where-Object { $candidate -match $_ }
    }
)
if ($forbidden.Count -gt 0) {
    throw "Forbidden local or secret path would be committed: $($forbidden -join ', ')"
}

$deepSeekKeyPattern = '(?i)\bsk-[a-z0-9_-]{20,}\b'
$possibleSecretFiles = [System.Collections.Generic.List[string]]::new()
foreach ($relativePath in $prospectiveFiles) {
    $absolutePath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
        continue
    }
    $item = Get-Item -LiteralPath $absolutePath
    if ($item.Length -gt 2MB) {
        continue
    }
    $content = Get-Content -LiteralPath $absolutePath -Raw -ErrorAction SilentlyContinue
    if ($null -ne $content -and $content -match $deepSeekKeyPattern) {
        $possibleSecretFiles.Add($relativePath)
    }
}
if ($possibleSecretFiles.Count -gt 0) {
    throw "A possible populated DeepSeek key was found in: $($possibleSecretFiles -join ', '). Values were not printed."
}

& (Join-Path $PSScriptRoot "demo-preflight.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Demo preflight failed."
}

Write-Host "Interview delivery verification passed." -ForegroundColor Green
Write-Host "Checked $($requiredRelativeFiles.Count) delivery files, $($markdownFiles.Count) Markdown files, and $($prospectiveFiles.Count) prospective Git files."
Write-Host "Docker was not required and DeepSeek was not called."
