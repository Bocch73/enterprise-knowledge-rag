[CmdletBinding()]
param(
    [switch]$RequireDocker
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$nodePath = Join-Path $projectRoot '.tools\node-v24.19.0-win-x64\node.exe'
$npmPath = Join-Path $projectRoot '.tools\node-v24.19.0-win-x64\npm.cmd'
$hasFailure = $false

function Write-CheckResult {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Details
    )

    $status = if ($Passed) { 'PASS' } else { 'FAIL' }
    Write-Host ("[{0}] {1}: {2}" -f $status, $Name, $Details)
}

if (Test-Path -LiteralPath $pythonPath) {
    $pythonVersion = & $pythonPath --version 2>&1
    Write-CheckResult -Name 'Python virtual environment' -Passed $true -Details $pythonVersion
} else {
    Write-CheckResult -Name 'Python virtual environment' -Passed $false -Details 'backend/.venv is missing'
    $hasFailure = $true
}

if ((Test-Path -LiteralPath $nodePath) -and (Test-Path -LiteralPath $npmPath)) {
    $nodeVersion = & $nodePath --version 2>&1
    $npmVersion = & $npmPath --version 2>&1
    Write-CheckResult -Name 'Project Node.js' -Passed ($nodeVersion -eq 'v24.19.0') -Details ("Node.js {0}, npm {1}" -f $nodeVersion, $npmVersion)
    if ($nodeVersion -ne 'v24.19.0') {
        $hasFailure = $true
    }
} else {
    Write-CheckResult -Name 'Project Node.js' -Passed $false -Details '.tools Node.js runtime is missing'
    $hasFailure = $true
}

$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if ($gitCommand) {
    $gitVersion = & git --version
    Write-CheckResult -Name 'Git' -Passed $true -Details $gitVersion
} else {
    Write-CheckResult -Name 'Git' -Passed $false -Details 'git command is unavailable'
    $hasFailure = $true
}

$codeCommand = Get-Command code -ErrorAction SilentlyContinue
if ($codeCommand) {
    $codeVersion = (& code --version | Select-Object -First 1)
    Write-CheckResult -Name 'Visual Studio Code' -Passed $true -Details ("version {0}" -f $codeVersion)
} else {
    Write-CheckResult -Name 'Visual Studio Code' -Passed $false -Details 'code command is unavailable'
    $hasFailure = $true
}

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCommand) {
    $dockerVersion = & docker --version 2>&1
    Write-CheckResult -Name 'Docker command' -Passed $true -Details $dockerVersion
} elseif ($RequireDocker) {
    Write-CheckResult -Name 'Docker command' -Passed $false -Details 'Docker Desktop is required but unavailable'
    $hasFailure = $true
} else {
    Write-Host '[WARN] Docker command: Docker Desktop is not installed yet; it becomes required before infrastructure work.'
}

if ($hasFailure) {
    exit 1
}

Write-Host 'Development environment verification completed.'
