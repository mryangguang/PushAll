$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "未找到 .venv，请先创建虚拟环境并安装依赖。" }

$desktop = [Environment]::GetFolderPath("Desktop")
if ([string]::IsNullOrWhiteSpace($desktop)) {
    $desktop = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Desktop"
}
$lnkPath = Join-Path $desktop "PushAll.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $pythonw
$lnk.Arguments = '"' + (Join-Path $root "desktop.py") + '"'
$lnk.WorkingDirectory = $root
$lnk.IconLocation = (Join-Path $root "app\web\icon.ico") + ",0"
$lnk.Description = "PushAll 消息中心"
$lnk.Save()

if (-not (Test-Path $lnkPath)) { throw "快捷方式创建失败：$lnkPath" }
Write-Output "已创建桌面快捷方式：$lnkPath"
