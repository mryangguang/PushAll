param(
    [switch]$SkipZip
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "未找到 .venv，请先安装依赖。" }

& $python -m PyInstaller --noconfirm --clean "packaging\PushAll.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

$dist = Join-Path $root "dist\PushAll"
Copy-Item "packaging\使用说明.txt" (Join-Path $dist "使用说明.txt") -Force
New-Item -ItemType Directory -Force -Path (Join-Path $dist "data"), (Join-Path $dist "plugins") | Out-Null
Set-Content -LiteralPath (Join-Path $dist "plugins\README.txt") -Encoding utf8 -Value "把插件目录放到这里，然后在程序「插件」页点刷新。也可以直接在插件页上传 zip 安装。"

if (-not $SkipZip) {
    $zip = Join-Path $root "dist\PushAll-0.1.0-win64.zip"
    if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
    Compress-Archive -Path $dist -DestinationPath $zip -CompressionLevel Optimal
    Write-Output "ZIP: $zip"
}

Write-Output "DIST: $dist"
