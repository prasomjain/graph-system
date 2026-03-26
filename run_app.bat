@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating Python virtual environment in .venv
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >NUL
python -m pip install -r backend\requirements.txt

if not exist "frontend\node_modules" (
  echo [setup] Installing frontend dependencies
  pushd frontend
  call npm install
  popd
)

if not exist ".env" (
  echo [setup] No .env file found. Copying backend\.env.example to .env
  copy /Y "backend\.env.example" ".env" >NUL
)

if "%GRAPH_DATA_PATH%"=="" set GRAPH_DATA_PATH=frontend/src/assets/processed_graph.json

start "DodgeAI Backend" cmd /k "cd /d %CD% && call .venv\Scripts\activate.bat && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"
start "DodgeAI Frontend" cmd /k "cd /d %CD%\frontend && npm run dev -- --host 0.0.0.0 --port 5173"

echo Dodge AI FDE Task is live at http://localhost:5173
