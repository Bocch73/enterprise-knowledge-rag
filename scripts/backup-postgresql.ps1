param(
    [string]$Database = "enterprise_rag",
    [string]$Username = "rag_app",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$PostgresBin = "C:\Program Files\PostgreSQL\17\bin",
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot "deploy\backups"
}

$pgDumpPath = Join-Path $PostgresBin "pg_dump.exe"
if (-not (Test-Path -LiteralPath $pgDumpPath -PathType Leaf)) {
    throw "pg_dump was not found: $pgDumpPath"
}
if ($Database -notmatch '^[A-Za-z][A-Za-z0-9_]{0,62}$') {
    throw "Database must be a simple PostgreSQL identifier."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$resolvedOutput = (Resolve-Path -LiteralPath $OutputDirectory).Path
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $resolvedOutput "$Database-$timestamp.dump"
$checksumPath = "$backupPath.sha256"

$securePassword = Read-Host "Database password for $Username" -AsSecureString
$plainPassword = [System.Net.NetworkCredential]::new("", $securePassword).Password
try {
    $env:PGPASSWORD = $plainPassword
    & $pgDumpPath --host $HostName --port $Port --username $Username `
        --dbname $Database --format custom --compress 9 --no-owner --no-privileges `
        --file $backupPath
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed with exit code $LASTEXITCODE"
    }

    $checksum = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText(
        $checksumPath,
        "$checksum  $([System.IO.Path]::GetFileName($backupPath))`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Backup created: $backupPath"
    Write-Host "SHA-256 checksum: $checksumPath"
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    $plainPassword = $null
    $securePassword.Dispose()
}
