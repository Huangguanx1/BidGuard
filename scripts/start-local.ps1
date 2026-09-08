param([switch]$OpenBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$node = (Get-Command node -ErrorAction Stop).Source
$logs = Join-Path $root 'data\logs'
if (-not (Test-Path $python)) { throw 'Missing .venv. Install backend dependencies first.' }
if (-not (Test-Path "$root\frontend\node_modules\vite\bin\vite.js")) { throw 'Run npm ci in frontend first.' }
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Start-ServiceIfNeeded($Port, $Executable, $Arguments, $Directory, $Name, $Url) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host "Port $Port is already in use; reusing the service if healthy."
    } else {
        $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $Directory -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs\$Name.log" -RedirectStandardError "$logs\$Name.error.log"
        Write-Host "$Name started (PID $($process.Id)). Logs: $logs"
    }
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        if ($process -and $process.HasExited) { throw "$Name exited. Check $logs\$Name.error.log" }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not become ready. Check $logs"
}

Start-ServiceIfNeeded 8000 $python '-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000' $root 'backend' 'http://127.0.0.1:8000/api/health'
Start-ServiceIfNeeded 5173 $node 'node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort' "$root\frontend" 'frontend' 'http://127.0.0.1:5173'
Write-Host 'BidGuard: http://127.0.0.1:5173'
Write-Host 'API docs: http://127.0.0.1:8000/docs'
if ($OpenBrowser) { Start-Process 'http://127.0.0.1:5173' }
