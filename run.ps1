param(
    [int]$Port = 8765,
    [switch]$Reload,
    [switch]$Desktop
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$env:PYTHONUTF8 = "1"

$python = Join-Path $root ".venv\Scripts\python.exe"
$pythonArgs = @()
if (-not (Test-Path $python)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $launcher) {
        throw "未找到 Python。请先安装 Python 3.11+，执行：python -m venv .venv"
    }
    $python = $launcher.Source
    $pythonArgs = @("-3")
}

if ($Desktop) {
    & $python @pythonArgs "$root\desktop.py"
    exit $LASTEXITCODE
}

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) { $uvicornArgs += "--reload" }
& $python @pythonArgs @uvicornArgs


