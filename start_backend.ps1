param(
    [string]$EnvName = "any-auto-register",
    [string]$PythonExe,
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$RestartExisting = $true
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "[INFO] 项目目录: $root"
$displayHost = if ($BindHost -eq "0.0.0.0") { "localhost" } else { $BindHost }
Write-Host "[INFO] 启动后端: http://$displayHost`:$Port"
Write-Host "[INFO] 按 Ctrl+C 可停止服务"

if ($RestartExisting) {
    Write-Host "[INFO] 启动前先清理旧的后端 / Solver 进程"
    & "$root\stop_backend.ps1" -BackendPort $Port -SolverPort 8889 -FullStop 0
}

$resolvedPythonExe = $null
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if ($PythonExe) {
    if (-not (Test-Path $PythonExe)) {
        Write-Error "指定的 Python 不存在: $PythonExe"
        exit 1
    }
    $resolvedPythonExe = (Resolve-Path $PythonExe).Path
    Write-Host "[INFO] 使用显式 Python: $resolvedPythonExe"
} elseif (Test-Path $venvPython) {
    $resolvedPythonExe = (Resolve-Path $venvPython).Path
    Write-Host "[INFO] 使用 uv/.venv 环境"
} else {
    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if (-not $conda) {
        Write-Error "未找到 .venv\Scripts\python.exe，也未找到 conda。请先执行 uv sync，或安装 Miniconda/Anaconda 后重试。"
        exit 1
    }

    Write-Host "[INFO] 使用 conda 环境: $EnvName"
    try {
        $resolvedPythonExe = (conda run --no-capture-output -n $EnvName python -c "import sys; print(sys.executable)").Trim()
    } catch {
        Write-Error "无法解析 conda 环境 '$EnvName' 对应的 python 路径。"
        exit 1
    }
}

if (-not (Test-Path $resolvedPythonExe)) {
    Write-Error "无法解析可用的 Python 路径。"
    exit 1
}

$env:HOST = $BindHost
$env:PORT = [string]$Port

Write-Host "[INFO] Python: $resolvedPythonExe"
& $resolvedPythonExe main.py
