[CmdletBinding()]
param(
    [ValidateSet("Start", "Stop", "Status", "Restart")]
    [string]$Action = "Start",

    [ValidateRange(5, 120)]
    [int]$StartupTimeoutSeconds = 30,

    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
$nodeDirectory = Join-Path $projectRoot ".tools\node-v24.19.0-win-x64"
$nodePath = Join-Path $nodeDirectory "node.exe"
$vitePath = Join-Path $frontendRoot "node_modules\vite\bin\vite.js"
$runtimeRoot = Join-Path $projectRoot ".dev-runtime"
$logRoot = Join-Path $runtimeRoot "logs"
$statePath = Join-Path $runtimeRoot "services.json"

function Get-ServiceDefinitions {
    $backendArguments = @("-m", "app.server")
    if (-not $NoReload) {
        $backendArguments += "--reload"
    }

    return @(
        [pscustomobject]@{
            Name = "backend"
            DisplayName = "Backend API"
            Executable = $pythonPath
            Arguments = $backendArguments
            WorkingDirectory = $backendRoot
            Port = 8000
            HealthUrl = "http://127.0.0.1:8000/api/v1/health/ready"
        },
        [pscustomobject]@{
            Name = "worker"
            DisplayName = "Document worker"
            Executable = $pythonPath
            Arguments = @("-m", "app.cli.run_ingestion_worker")
            WorkingDirectory = $backendRoot
            Port = $null
            HealthUrl = $null
        },
        [pscustomobject]@{
            Name = "frontend"
            DisplayName = "Frontend"
            Executable = $nodePath
            Arguments = @($vitePath)
            WorkingDirectory = $frontendRoot
            Port = 5173
            HealthUrl = "http://127.0.0.1:5173"
        }
    )
}

function Read-ServiceState {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        return @()
    }

    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        return @($state.services)
    }
    catch {
        throw "Cannot read the local service state file: $statePath. Verify the file before removing it."
    }
}

function Test-TrackedProcess {
    param([Parameter(Mandatory)]$ServiceRecord)

    try {
        $process = Get-Process -Id ([int]$ServiceRecord.pid) -ErrorAction Stop
        $expectedExecutable = [System.IO.Path]::GetFullPath([string]$ServiceRecord.executable)
        $actualExecutable = [System.IO.Path]::GetFullPath($process.Path)
        if (-not $expectedExecutable.Equals($actualExecutable, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $false
        }

        $expectedStart = [DateTimeOffset]::Parse([string]$ServiceRecord.startedAtUtc)
        $actualStart = [DateTimeOffset]::new($process.StartTime.ToUniversalTime())
        return [Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -lt 5
    }
    catch {
        return $false
    }
}

function Get-DescendantProcessIds {
    param([Parameter(Mandatory)][int]$ParentProcessId)

    $allProcesses = @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId)
    $pending = [System.Collections.Generic.Queue[int]]::new()
    $descendants = [System.Collections.Generic.List[int]]::new()
    $pending.Enqueue($ParentProcessId)

    while ($pending.Count -gt 0) {
        $currentParent = $pending.Dequeue()
        foreach ($child in $allProcesses | Where-Object { $_.ParentProcessId -eq $currentParent }) {
            $childId = [int]$child.ProcessId
            $descendants.Add($childId)
            $pending.Enqueue($childId)
        }
    }

    return @($descendants)
}

function Stop-ServiceRecords {
    param([Parameter(Mandatory)][array]$ServiceRecords)

    foreach ($service in $ServiceRecords) {
        if (-not (Test-TrackedProcess -ServiceRecord $service)) {
            Write-Host "[stopped] $($service.displayName)" -ForegroundColor DarkGray
            continue
        }

        $processIds = @(Get-DescendantProcessIds -ParentProcessId ([int]$service.pid))
        [array]::Reverse($processIds)
        $processIds += [int]$service.pid

        foreach ($processId in $processIds) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
        Write-Host "[stopped] $($service.displayName)" -ForegroundColor Yellow
    }
}

function Test-PortAvailable {
    param([Parameter(Mandatory)][int]$Port)

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $listener.Start()
        return $true
    }
    catch [System.Net.Sockets.SocketException] {
        return $false
    }
    finally {
        $listener.Stop()
    }
}

function Wait-ForHttpEndpoint {
    param(
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][string]$DisplayName
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 3 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "$DisplayName did not pass its startup check within $StartupTimeoutSeconds seconds: $Url"
}

function Assert-StartPrerequisites {
    $requiredFiles = @(
        @{ Path = $pythonPath; Message = "Backend virtual environment was not found: $pythonPath" },
        @{ Path = (Join-Path $backendRoot ".env"); Message = "backend/.env is missing. Copy .env.example and fill in the local values first." },
        @{ Path = $nodePath; Message = "Project Node.js was not found: $nodePath" },
        @{ Path = $vitePath; Message = "Frontend dependencies were not found. Run npm ci in frontend first." }
    )

    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $requiredFile.Path -PathType Leaf)) {
            throw $requiredFile.Message
        }
    }

    foreach ($definition in Get-ServiceDefinitions) {
        if ($null -ne $definition.Port -and -not (Test-PortAvailable -Port $definition.Port)) {
            throw "Port $($definition.Port) is already in use. Cannot start $($definition.DisplayName)."
        }
    }
}

function Show-ServiceStatus {
    $services = @(Read-ServiceState)
    if ($services.Count -eq 0) {
        Write-Host "No services have been started by this launcher." -ForegroundColor DarkGray
        return
    }

    $rows = foreach ($service in $services) {
        [pscustomobject]@{
            Service = $service.displayName
            ProcessId = $service.pid
            Status = if (Test-TrackedProcess -ServiceRecord $service) { "Running" } else { "Stopped" }
            Address = if ($service.name -eq "backend") {
                "http://127.0.0.1:8000/docs"
            } elseif ($service.name -eq "frontend") {
                "http://127.0.0.1:5173"
            } else {
                "-"
            }
        }
    }

    $rows | Format-Table -AutoSize
    Write-Host "Log directory: $logRoot"
}

function Stop-DevelopmentServices {
    $services = @(Read-ServiceState)
    if ($services.Count -eq 0) {
        Write-Host "There are no services to stop." -ForegroundColor DarkGray
        return
    }

    Stop-ServiceRecords -ServiceRecords $services
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    Write-Host "All local development services have stopped." -ForegroundColor Green
}

function Start-DevelopmentServices {
    $existingServices = @(Read-ServiceState)
    $runningServices = @($existingServices | Where-Object { Test-TrackedProcess -ServiceRecord $_ })
    if ($runningServices.Count -gt 0) {
        Show-ServiceStatus
        throw "Services are already running. Use -Action Stop or -Action Restart first."
    }

    Assert-StartPrerequisites
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

    $runId = Get-Date -Format "yyyyMMdd-HHmmss"
    $startedServices = [System.Collections.Generic.List[object]]::new()

    try {
        foreach ($definition in Get-ServiceDefinitions) {
            $stdoutPath = Join-Path $logRoot "$runId-$($definition.Name).out.log"
            $stderrPath = Join-Path $logRoot "$runId-$($definition.Name).error.log"
            $process = Start-Process `
                -FilePath $definition.Executable `
                -ArgumentList $definition.Arguments `
                -WorkingDirectory $definition.WorkingDirectory `
                -RedirectStandardOutput $stdoutPath `
                -RedirectStandardError $stderrPath `
                -WindowStyle Hidden `
                -PassThru

            Start-Sleep -Milliseconds 500
            if ($process.HasExited) {
                throw "$($definition.DisplayName) exited during startup. Read the log: $stderrPath"
            }

            $startedServices.Add([pscustomobject]@{
                name = $definition.Name
                displayName = $definition.DisplayName
                pid = $process.Id
                startedAtUtc = ([DateTimeOffset]::new($process.StartTime.ToUniversalTime())).ToString("O")
                executable = $definition.Executable
                standardOutputLog = $stdoutPath
                standardErrorLog = $stderrPath
            })
            Write-Host "[started] $($definition.DisplayName), process ID $($process.Id)" -ForegroundColor Cyan
        }

        $state = [pscustomobject]@{
            runId = $runId
            createdAtUtc = [DateTimeOffset]::UtcNow.ToString("O")
            services = @($startedServices)
        }
        $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding utf8

        foreach ($definition in Get-ServiceDefinitions) {
            if ($null -ne $definition.HealthUrl) {
                Wait-ForHttpEndpoint -Url $definition.HealthUrl -DisplayName $definition.DisplayName
                Write-Host "[ready] $($definition.DisplayName)" -ForegroundColor Green
            }
        }
    }
    catch {
        Stop-ServiceRecords -ServiceRecords @($startedServices)
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
        throw
    }

    Write-Host ""
    Write-Host "All three independent processes are running." -ForegroundColor Green
    Write-Host "Frontend: http://127.0.0.1:5173"
    Write-Host "API documentation: http://127.0.0.1:8000/docs"
    Write-Host "Status: powershell -ExecutionPolicy Bypass -File .\scripts\dev-services.ps1 -Action Status"
    Write-Host "Stop: powershell -ExecutionPolicy Bypass -File .\scripts\dev-services.ps1 -Action Stop"
    Write-Host "Log directory: $logRoot"
}

switch ($Action) {
    "Start" { Start-DevelopmentServices }
    "Stop" { Stop-DevelopmentServices }
    "Status" { Show-ServiceStatus }
    "Restart" {
        Stop-DevelopmentServices
        Start-DevelopmentServices
    }
}
