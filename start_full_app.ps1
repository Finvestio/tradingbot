# Trading Bot Full Application Startup Script
# This script starts both the FastAPI backend and Angular frontend

Write-Host "🎯 Starting Trading Bot Full Application" -ForegroundColor Green
Write-Host "=" * 50

# Function to start backend
function Start-Backend {
    Write-Host "🚀 Starting FastAPI backend on http://localhost:8081..." -ForegroundColor Yellow
    $backendProcess = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8081", "--reload" -PassThru -WorkingDirectory $PWD
    return $backendProcess
}

# Function to start frontend
function Start-Frontend {
    Write-Host "🚀 Starting Angular frontend on http://localhost:4200..." -ForegroundColor Yellow
    $frontendDir = Join-Path $PWD "trading-dashboard"
    
    # Check if node_modules exists
    if (!(Test-Path (Join-Path $frontendDir "node_modules"))) {
        Write-Host "📦 Installing npm dependencies..." -ForegroundColor Cyan
        Set-Location $frontendDir
        npm install
        Set-Location ..
    }
    
    $frontendProcess = Start-Process -FilePath "npm" -ArgumentList "start" -PassThru -WorkingDirectory $frontendDir
    return $frontendProcess
}

try {
    # Start backend
    $backendProcess = Start-Backend
    Start-Sleep -Seconds 3
    
    # Start frontend  
    $frontendProcess = Start-Frontend
    
    Write-Host ""
    Write-Host "✅ Both servers started successfully!" -ForegroundColor Green
    Write-Host "📊 Backend API: http://localhost:8081" -ForegroundColor Cyan
    Write-Host "🌐 Frontend UI: http://localhost:4200" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Press Ctrl+C to stop both servers..." -ForegroundColor Yellow
    
    # Wait for user input to stop
    Read-Host "Press Enter to stop the servers"
}
finally {
    Write-Host "🛑 Shutting down servers..." -ForegroundColor Red
    
    # Stop processes
    if ($backendProcess -and !$backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force
        Write-Host "Backend stopped" -ForegroundColor Yellow
    }
    
    if ($frontendProcess -and !$frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force
        Write-Host "Frontend stopped" -ForegroundColor Yellow
    }
    
    Write-Host "✅ Servers stopped successfully" -ForegroundColor Green
}