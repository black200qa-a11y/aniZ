@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo [Aniz] Checking local configuration...
if not exist ".env" (
  echo [ERROR] .env was not found. Copy pc.env.example to .env and fill the secrets first.
  pause
  exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "ARIA2_SECRET=" .env`) do set "ARIA2_SECRET=%%B"
if not defined ARIA2_SECRET (
  echo [ERROR] ARIA2_SECRET is missing from .env
  pause
  exit /b 1
)

where aria2c >nul 2>&1
if errorlevel 1 (
  echo [ERROR] aria2c was not found on PATH.
  pause
  exit /b 1
)
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found on PATH.
  pause
  exit /b 1
)

if not exist "temp_downloads" mkdir "temp_downloads"

echo [Aniz] Starting aria2 JSON-RPC...
start "Aniz - aria2" cmd /k "aria2c --enable-rpc=true --rpc-listen-all=false --rpc-listen-port=6800 --rpc-secret=\"%ARIA2_SECRET%\" --dir=\"%CD%\temp_downloads\" --seed-time=0"

timeout /t 2 /nobreak >nul

echo [Aniz] Starting worker...
start "Aniz - worker" cmd /k "python -m aniz_pipeline.main"

echo [Aniz] Starting Telegram admin bot...
start "Aniz - Telegram admin bot" cmd /k "python -m app.bot.runner"

echo.
echo [Aniz] Three local terminals were started. Close them to stop the services.
endlocal
