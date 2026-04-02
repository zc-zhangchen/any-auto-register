@echo off
setlocal

set "VENV_DIR=%APP_VENV_DIR%"
if "%VENV_DIR%"=="" set "VENV_DIR=.venv"
set "HOST=%HOST%"
if "%HOST%"=="" set "HOST=0.0.0.0"
set "PORT=%PORT%"
if "%PORT%"=="" set "PORT=8000"
set "RESTART_EXISTING=%RESTART_EXISTING%"
if "%RESTART_EXISTING%"=="" set "RESTART_EXISTING=1"

cd /d "%~dp0"
if "%VENV_DIR:~1,1%"==":" (
  set "VIRTUAL_ENV=%VENV_DIR%"
) else (
  for %%I in ("%CD%\%VENV_DIR%") do set "VIRTUAL_ENV=%%~fI"
)
set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
set "DISPLAY_HOST=%HOST%"
if "%DISPLAY_HOST%"=="0.0.0.0" set "DISPLAY_HOST=localhost"

echo [INFO] 项目目录: %CD%
echo [INFO] 使用虚拟环境: %VIRTUAL_ENV%
echo [INFO] 启动后端: http://%DISPLAY_HOST%:%PORT%
echo [INFO] 按 Ctrl+C 可停止服务

if "%RESTART_EXISTING%"=="1" (
  echo [INFO] 启动前先清理旧的后端 / Solver 进程
  where pwsh >nul 2>nul
  if errorlevel 1 (
    powershell -ExecutionPolicy Bypass -File "%~dp0stop_backend.ps1" -BackendPort %PORT% -SolverPort 8889 -FullStop 0
  ) else (
    pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_backend.ps1" -BackendPort %PORT% -SolverPort 8889 -FullStop 0
  )
)

if not exist "%PYTHON_EXE%" (
  echo [ERROR] 未找到虚拟环境 Python: %PYTHON_EXE%
  echo [ERROR] 请先执行 uv sync 初始化项目环境。
  exit /b 1
)

set "APP_VENV_DIR=%VENV_DIR%"
set "PATH=%VIRTUAL_ENV%\Scripts;%PATH%"
echo [INFO] Python: %PYTHON_EXE%
"%PYTHON_EXE%" main.py
