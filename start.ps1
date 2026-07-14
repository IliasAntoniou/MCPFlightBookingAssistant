# Start script for MCPFlightBooking system
# This script starts all required services in separate terminals

Write-Host "Starting MCPFlightBooking System..." -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $rootDir "..\.venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $rootDir ".venv\Scripts\python.exe"
}

if (-not (Test-Path $pythonExe)) {
    Write-Host "Could not find a virtual environment Python executable." -ForegroundColor Red
    Write-Host "Expected one of:" -ForegroundColor Yellow
    Write-Host "  - $(Join-Path $rootDir '..\.venv\Scripts\python.exe')" -ForegroundColor White
    Write-Host "  - $(Join-Path $rootDir '.venv\Scripts\python.exe')" -ForegroundColor White
    Write-Host ""
    Write-Host "Create/install dependencies with:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv" -ForegroundColor White
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r MCPFlightBooking\requirements.txt" -ForegroundColor White
    exit 1
}

Write-Host "Using Python: $pythonExe" -ForegroundColor DarkGray

# Start Ollama Server
Write-Host "[1/4] Starting Ollama Server on port 11434..." -ForegroundColor Yellow
$commandOllama = "Write-Host 'Ollama Server' -ForegroundColor Yellow; ollama serve"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $commandOllama

# Wait for Ollama to start
Start-Sleep -Seconds 5

# Start Flight API (Backend Database)
Write-Host "[2/4] Starting Flight API on port 8000..." -ForegroundColor Green
$backendDir = Join-Path $rootDir "src\backend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendDir'; Write-Host 'Flight API Server' -ForegroundColor Cyan; & '$pythonExe' -m uvicorn flight_api:app --reload --port 8000"

# Wait a bit for backend to start
Start-Sleep -Seconds 3

# Start Backend Server (Gemini + MCP)
Write-Host "[3/4] Starting Gemini + MCP Server on port 8001..." -ForegroundColor Green
$backendServerDir = Join-Path $rootDir "src\backend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendServerDir'; Write-Host 'Gemini + MCP Server' -ForegroundColor Magenta; & '$pythonExe' -m uvicorn host:app --reload --port 8001"

# Wait a bit for frontend to start
Start-Sleep -Seconds 3

# Open the webpage
Write-Host "[4/4] Opening webpage..." -ForegroundColor Green
$frontendDir = Join-Path $rootDir "src\frontend"
$indexPath = Join-Path $frontendDir "index.html"
Start-Process $indexPath

Write-Host ""
Write-Host "All services started successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Services running:" -ForegroundColor Cyan
Write-Host "  - Ollama:            http://localhost:11434" -ForegroundColor White
Write-Host "  - Flight API:        http://localhost:8000" -ForegroundColor White
Write-Host "  - Gemini + MCP:      http://localhost:8001" -ForegroundColor White
Write-Host "  - Frontend:          Browser opened" -ForegroundColor White
Write-Host ""
Write-Host "Close the PowerShell windows to stop the servers." -ForegroundColor Yellow
