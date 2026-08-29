param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot "backend\.env"
$postgresRoot = "C:\Program Files\PostgreSQL\17\bin"
$psqlPath = Join-Path $postgresRoot "psql.exe"
$createdbPath = Join-Path $postgresRoot "createdb.exe"

if (-not (Test-Path -LiteralPath $psqlPath)) {
    throw "未找到 PostgreSQL 17 命令行工具：$psqlPath"
}

if ((Test-Path -LiteralPath $envPath) -and -not $Force) {
    throw "配置文件已经存在：$envPath。若确定需要重新生成，请添加 -Force。"
}

function Invoke-PostgresCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & $psqlPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL 命令执行失败，退出码：$LASTEXITCODE"
    }
    return $output
}

Write-Host "即将创建本地开发数据库 enterprise_rag 和受限账号 rag_app。"
Write-Host "输入安装 PostgreSQL 时设置的 postgres 管理员密码；输入内容不会显示。"
$secureAdminPassword = Read-Host "postgres 管理员密码" -AsSecureString
$adminPassword = [System.Net.NetworkCredential]::new("", $secureAdminPassword).Password

if ([string]::IsNullOrWhiteSpace($adminPassword)) {
    throw "管理员密码不能为空。"
}

$applicationPassword = [Convert]::ToHexString(
    [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)
).ToLowerInvariant()
$jwtSecret = [Convert]::ToHexString(
    [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()

$connectionArguments = @(
    "-w", "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "-d", "postgres",
    "-v", "ON_ERROR_STOP=1"
)

try {
    $env:PGPASSWORD = $adminPassword
    Invoke-PostgresCommand ($connectionArguments + @("-tAc", "SELECT 1;")) | Out-Null

    $roleExists = Invoke-PostgresCommand (
        $connectionArguments + @("-tAc", "SELECT 1 FROM pg_roles WHERE rolname = 'rag_app';")
    )

    if (($roleExists | Out-String).Trim() -eq "1") {
        $roleSql = "ALTER ROLE rag_app WITH LOGIN PASSWORD '$applicationPassword' " +
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;"
        Invoke-PostgresCommand ($connectionArguments + @("-c", $roleSql)) | Out-Null
        Write-Host "已更新现有 rag_app 账号的本地开发密码。"
    }
    else {
        $roleSql = "CREATE ROLE rag_app WITH LOGIN PASSWORD '$applicationPassword' " +
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;"
        Invoke-PostgresCommand ($connectionArguments + @("-c", $roleSql)) | Out-Null
        Write-Host "已创建受限数据库账号 rag_app。"
    }

    $databaseExists = Invoke-PostgresCommand (
        $connectionArguments + @("-tAc", "SELECT 1 FROM pg_database WHERE datname = 'enterprise_rag';")
    )

    if (($databaseExists | Out-String).Trim() -ne "1") {
        & $createdbPath -w -h 127.0.0.1 -p 5432 -U postgres -O rag_app -E UTF8 enterprise_rag
        if ($LASTEXITCODE -ne 0) {
            throw "创建 enterprise_rag 数据库失败，退出码：$LASTEXITCODE"
        }
        Write-Host "已创建 UTF-8 数据库 enterprise_rag。"
    }
    else {
        Invoke-PostgresCommand (
            $connectionArguments + @("-c", "ALTER DATABASE enterprise_rag OWNER TO rag_app;")
        ) | Out-Null
        Write-Host "数据库 enterprise_rag 已存在，已确认所有者为 rag_app。"
    }

    $env:PGPASSWORD = $applicationPassword
    & $psqlPath -w -h 127.0.0.1 -p 5432 -U rag_app -d enterprise_rag -tAc `
        "SELECT current_user, current_database();" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "应用账号连接验证失败，退出码：$LASTEXITCODE"
    }

    $environmentFile = @(
        "RAG_APP_NAME=Enterprise Knowledge RAG"
        "RAG_APP_VERSION=0.1.0"
        "RAG_ENVIRONMENT=local"
        "RAG_DEBUG=false"
        "RAG_API_V1_PREFIX=/api/v1"
        "RAG_LOG_LEVEL=INFO"
        "RAG_DOCS_ENABLED=true"
        "RAG_REQUEST_ID_HEADER=X-Request-ID"
        "RAG_READINESS_TIMEOUT_SECONDS=2.0"
        "RAG_DATABASE_URL=postgresql+psycopg://rag_app:$applicationPassword@127.0.0.1:5432/enterprise_rag"
        "RAG_DATABASE_POOL_SIZE=5"
        "RAG_DATABASE_MAX_OVERFLOW=10"
        "RAG_JWT_SECRET=$jwtSecret"
        "RAG_ACCESS_TOKEN_EXPIRE_MINUTES=15"
        ""
    ) -join [Environment]::NewLine

    [System.IO.File]::WriteAllText(
        $envPath,
        $environmentFile,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Host "已生成本地私密配置：$envPath"
    Write-Host "数据库引导完成。不要把 backend\.env 提交到 Git。"
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    $adminPassword = $null
    $secureAdminPassword.Dispose()
}
