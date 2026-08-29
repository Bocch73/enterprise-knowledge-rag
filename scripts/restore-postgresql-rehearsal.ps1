param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [Parameter(Mandatory = $true)]
    [string]$TargetDatabase,
    [Parameter(Mandatory = $true)]
    [string]$ConfirmTargetDatabase,
    [string]$OwnerUsername = "rag_app",
    [string]$AdminUsername = "postgres",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$PostgresBin = "C:\Program Files\PostgreSQL\17\bin"
)

$ErrorActionPreference = "Stop"
$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
$createdbPath = Join-Path $PostgresBin "createdb.exe"
$pgRestorePath = Join-Path $PostgresBin "pg_restore.exe"
$psqlPath = Join-Path $PostgresBin "psql.exe"

foreach ($toolPath in @($createdbPath, $pgRestorePath, $psqlPath)) {
    if (-not (Test-Path -LiteralPath $toolPath -PathType Leaf)) {
        throw "PostgreSQL tool was not found: $toolPath"
    }
}
if ($TargetDatabase -notmatch '^[A-Za-z][A-Za-z0-9_]{0,62}_restore$') {
    throw "Safety rule: the rehearsal database name must end with _restore."
}
if ($ConfirmTargetDatabase -cne $TargetDatabase) {
    throw "Confirmation does not exactly match the target database name."
}

$checksumPath = "$resolvedBackup.sha256"
if (Test-Path -LiteralPath $checksumPath -PathType Leaf) {
    $expectedChecksum = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\s+')[0]
    $actualChecksum = (Get-FileHash -LiteralPath $resolvedBackup -Algorithm SHA256).Hash
    if ($actualChecksum -cne $expectedChecksum) {
        throw "Backup checksum verification failed."
    }
}

& $pgRestorePath --list $resolvedBackup | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The backup archive cannot be read by pg_restore."
}

$securePassword = Read-Host "Database administrator password for $AdminUsername" -AsSecureString
$plainPassword = [System.Net.NetworkCredential]::new("", $securePassword).Password
try {
    $env:PGPASSWORD = $plainPassword
    $existing = & $psqlPath --no-password --host $HostName --port $Port `
        --username $AdminUsername --dbname postgres --tuples-only --no-align `
        --command "SELECT 1 FROM pg_database WHERE datname = '$TargetDatabase';"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not check the target database."
    }
    if (($existing | Out-String).Trim() -eq "1") {
        throw "Target database already exists. This script never overwrites an existing database."
    }

    & $createdbPath --no-password --host $HostName --port $Port `
        --username $AdminUsername --owner $OwnerUsername --encoding UTF8 $TargetDatabase
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the rehearsal database."
    }

    & $pgRestorePath --no-password --host $HostName --port $Port `
        --username $AdminUsername --dbname $TargetDatabase --exit-on-error `
        --no-owner --no-privileges $resolvedBackup
    if ($LASTEXITCODE -ne 0) {
        throw "Restore failed. Keep the rehearsal database for diagnosis."
    }
    Write-Host "Restore rehearsal completed in database: $TargetDatabase"
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    $plainPassword = $null
    $securePassword.Dispose()
}
