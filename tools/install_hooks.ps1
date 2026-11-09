$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
git config core.hooksPath .githooks
Write-Output "已启用 .githooks/pre-push（每次 git push 前自动检查）"
