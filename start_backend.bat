@echo off
setlocal

set "ENV_NAME=%APP_CONDA_ENV%"
if "%ENV_NAME%"=="" set "ENV_NAME=any-auto-register"
set "PYTHON_EXE=%APP_PYTHON_EXE%"
set "HOST=%HOST%"
if "%HOST%"=="" set "HOST=0.0.0.0"
set "PORT=%PORT%"
if "%PORT%"=="" set "PORT=8000"
set "RESTART_EXISTING=%RESTART_EXISTING%"
if "%RESTART_EXISTING%"=="" set "RESTART_EXISTING=1"

cd /d "%~dp0"
echo [INFO] 项目目录: %CD%
echo [INFO] 启动后端: http://localhost:%PORT%
echo [INFO] 按 Ctrl+C 可停止服务

if "%RESTART_EXISTING%"=="1" (
  echo [INFO] 启动前先清理旧的后端 / Solver 进程
  powershell -ExecutionPolicy Bypass -File "%~dp0stop_backend.ps1" -BackendPort %PORT% -SolverPort 8889 -FullStop 0
)

if not "%PYTHON_EXE%"=="" goto validate_python

if exist "%~dp0.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
  echo [INFO] 使用 uv/.venv 环境
) else (
  where conda >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] 未找到 .venv\Scripts\python.exe，也未找到 conda。请先执行 uv sync，或安装 Miniconda/Anaconda 后重试。
    exit /b 1
  )
  echo [INFO] 使用 conda 环境: %ENV_NAME%
  for /f "usebackq delims=" %%i in (`conda run --no-capture-output -n %ENV_NAME% python -c "import sys; print(sys.executable)"`) do set "PYTHON_EXE=%%i"
)

:validate_python
if not exist "%PYTHON_EXE%" (
  echo [ERROR] 无法解析可用的 Python 路径: %PYTHON_EXE%
  exit /b 1
)

set "HOST=%HOST%"
set "PORT=%PORT%"
echo [INFO] Python: %PYTHON_EXE%
"%PYTHON_EXE%" main.py
