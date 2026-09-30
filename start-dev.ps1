# Start AuditMind for development: the backend (API), the background worker
# and the frontend, each in its own window. Run from anywhere:
#
#   powershell -ExecutionPolicy Bypass -File S:\AI-Projects\AuditMind\start-dev.ps1
#
# Ctrl+C in a window stops that part. The worker finishes the job it's
# running first; a second Ctrl+C, or closing its window, stops it at once,
# and what it was running is picked up again the next time it starts.

$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Open-Window($title, $folder, $command) {
    $script = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$folder'; $command"
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $script -WorkingDirectory $folder
}

Open-Window 'AuditMind backend' $backend '.\.venv\Scripts\uvicorn.exe app.main:app --reload'
Open-Window 'AuditMind worker' $backend '.\.venv\Scripts\python.exe -m app.worker'
Open-Window 'AuditMind frontend' $frontend 'npm run dev'

Write-Host 'Started: backend http://localhost:8000, frontend http://localhost:3000, and the background worker.'
