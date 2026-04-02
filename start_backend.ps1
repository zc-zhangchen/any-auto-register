param(
    [string]$VenvDir = ".venv",
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$RestartExisting = $true
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not $PSBoundParameters.ContainsKey("VenvDir") -and $env:APP_VENV_DIR) {
    $VenvDir = $env:APP_VENV_DIR
}

$venvPath = if ([IO.Path]::IsPathRooted($VenvDir)) { $VenvDir } else { Join-Path $root $VenvDir }
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

Write-Host "[INFO] 项目目录: $root"
Write-Host "[INFO] 使用虚拟环境: $venvPath"
$displayHost = if ($BindHost -eq "0.0.0.0") { "localhost" } else { $BindHost }
Write-Host "[INFO] 启动后端: http://$displayHost`:$Port"
Write-Host "[INFO] 按 Ctrl+C 可停止服务"

if ($RestartExisting) {
    Write-Host "[INFO] 启动前先清理旧的后端 / Solver 进程"
    & "$root\stop_backend.ps1" -BackendPort $Port -SolverPort 8889 -FullStop 0
}

if (-not (Test-Path $pythonExe)) {
    Write-Error "未找到虚拟环境 Python：$pythonExe。请先执行 'uv sync' 初始化项目环境。"
    exit 1
}

$resolvedVenvPath = (Resolve-Path $venvPath).Path
$env:APP_VENV_DIR = $VenvDir
$env:HOST = $BindHost
$env:PORT = [string]$Port
$env:VIRTUAL_ENV = $resolvedVenvPath
$env:PATH = (Join-Path $resolvedVenvPath "Scripts") + [IO.Path]::PathSeparator + $env:PATH

Write-Host "[INFO] Python: $pythonExe"
& $pythonExe main.py
