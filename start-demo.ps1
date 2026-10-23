param([switch]$Stop, [switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$demoRoot = $PSScriptRoot
$demoState = Join-Path $demoRoot 'temp\auditmind-demo'
$demoPidFile = Join-Path $demoState 'processes.json'

function Stop-Demo {
    if (-not (Test-Path -LiteralPath $demoPidFile)) { return }
    foreach ($record in (Get-Content -LiteralPath $demoPidFile -Raw | ConvertFrom-Json)) {
        $process = Get-Process -Id $record.Id -ErrorAction SilentlyContinue
        # PID reuse must not stop a different application.
        if ($process -and $process.StartTime.ToUniversalTime().ToString('o') -eq $record.Started) {
            Stop-Process -Id $record.Id
        }
    }
    Remove-Item -LiteralPath $demoPidFile
}

if ($Stop) { Stop-Demo; Write-Host 'Demo services stopped. Demo data retained.'; exit 0 }
$previousBackendUrl = $env:BACKEND_URL
$previousApiUrl = $env:NEXT_PUBLIC_API_URL
try {
# Override stale personal frontend .env settings for both build and runtime.
$env:BACKEND_URL = 'http://127.0.0.1:8000'
$env:NEXT_PUBLIC_API_URL = '/api/v1'
foreach ($port in @(3000, 8000)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop its application (or this demo with -Stop) before starting."
    }
}
if (Test-Path -LiteralPath $demoPidFile) {
    throw 'A previous demo process record exists. Run start-demo.ps1 -Stop first; it preserves demo data.'
}
$demoPython = Join-Path $demoRoot 'backend\.venv\Scripts\python.exe'
$demoNext = Join-Path $demoRoot 'frontend\node_modules\next\dist\bin\next'
if (-not (Test-Path -LiteralPath $demoPython) -or -not (Test-Path -LiteralPath $demoNext)) {
    throw 'Install backend requirements-dev.txt and frontend npm dependencies first; see docs/USER_MANUAL.md.'
}
New-Item -ItemType Directory -Force -Path $demoState | Out-Null
Push-Location (Join-Path $demoRoot 'backend')
try {
    & $demoPython scripts/demo.py prepare
    if ($LASTEXITCODE -ne 0) { throw 'Demo database preparation failed; no services started.' }
} finally { Pop-Location }
Push-Location (Join-Path $demoRoot 'frontend')
try {
    if (-not $SkipBuild) {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed; no services started.' }
        Get-Content -LiteralPath '.next\BUILD_ID' | Set-Content -LiteralPath (Join-Path $demoState 'build-id.txt')
    } elseif (-not (Test-Path -LiteralPath '.next\BUILD_ID')) {
        throw 'No production build exists. Run again without -SkipBuild.'
    } elseif (-not (Test-Path -LiteralPath (Join-Path $demoState 'build-id.txt')) -or
        (Get-Content -LiteralPath '.next\BUILD_ID' -Raw).Trim() -ne (Get-Content -LiteralPath (Join-Path $demoState 'build-id.txt') -Raw).Trim()) {
        throw 'This build was not prepared for the demo. Run again without -SkipBuild.'
    }
} finally { Pop-Location }
$demoProcesses = @()
try {
    foreach ($service in @('api', 'worker', 'frontend')) {
        if ($service -eq 'frontend') {
            $executable = (Get-Command node.exe).Source
            $arguments = @(('"' + $demoNext + '"'), 'start', '--hostname', '127.0.0.1', '--port', '3000')
            $folder = Join-Path $demoRoot 'frontend'
        } else {
            $executable = $demoPython
            $arguments = @('scripts/demo.py', $service)
            $folder = Join-Path $demoRoot 'backend'
        }
        $process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $folder -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $demoState "$service.log") -RedirectStandardError (Join-Path $demoState "$service.error.log")
        $demoProcesses += @{ Id = $process.Id; Started = $process.StartTime.ToUniversalTime().ToString('o') }
        $demoProcesses | ConvertTo-Json | Set-Content -LiteralPath $demoPidFile
    }
    foreach ($url in @('http://127.0.0.1:8000/health', 'http://127.0.0.1:3000/login', 'http://127.0.0.1:3000/api/v1/auth/options')) {
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            try { $null = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2; $ready = $true; break }
            catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $ready) { throw "Service did not become ready: $url. Inspect $demoState logs." }
    }
    Write-Host 'Ready: http://localhost:3000/login (local-only synthetic demo; no external AI credentials).'
    Write-Host 'Stop with: powershell -ExecutionPolicy Bypass -File .\start-demo.ps1 -Stop'
} catch { Stop-Demo; throw }
} finally {
    $env:BACKEND_URL = $previousBackendUrl
    $env:NEXT_PUBLIC_API_URL = $previousApiUrl
}
