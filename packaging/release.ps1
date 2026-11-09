param(
    [string]$NotesFile = "",
    [switch]$SkipPush,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$versionMatch = Select-String -Path "app\settings.py" -Pattern '^VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionMatch) { throw "Cannot read VERSION from app\settings.py" }
$version = $versionMatch.Matches[0].Groups[1].Value
$tag = "v$version"
$releaseName = "PushAll $tag"

$zip = Join-Path $root "dist\PushAll-$version-win64.zip"
$sha = "$zip.sha256"
$zipName = Split-Path -Leaf $zip

if (-not (Test-Path $zip)) {
    Write-Output "Package not found, building..."
    & (Join-Path $root "packaging\build.ps1")
}
if (-not (Test-Path $sha)) {
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
    "$hash  $zipName" | Set-Content -LiteralPath $sha -Encoding ascii
}

$body = "Windows 便携版（解压即用）`n`n- 内置 Python 运行时，目标电脑无需安装 Python`n- 解压后双击 PushAll.exe 启动`n- 数据、日志、插件均在 exe 同目录`n- 关闭/最小化收进系统托盘"
if ($NotesFile -and (Test-Path $NotesFile)) {
    $body = Get-Content -LiteralPath $NotesFile -Raw
}

if ($DryRun) {
    Write-Output "version:  $version"
    Write-Output "tag:      $tag"
    Write-Output "name:     $releaseName"
    Write-Output "zip:      $zip"
    Write-Output "sha:      $sha"
    Write-Output "body:"
    Write-Output $body
    exit 0
}

$env:GIT_TERMINAL_PROMPT = "0"
if (-not $SkipPush) {
    git tag -f $tag
    git push origin main
    git push -f origin $tag
}

$cred = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
$token = (($cred | Select-String '^password=').Line -replace '^password=','')
if (-not $token) { throw "No GitHub token found in git credential manager" }
$headers = @{ Authorization = "token $token"; Accept = "application/vnd.github+json"; "User-Agent" = "PushAll-Release" }

$repo = "mryangguang/PushAll"
$release = $null
try {
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/tags/$tag" -Headers $headers
} catch {
    $release = $null
}

$payload = @{ name = $releaseName; body = $body; draft = $false; prerelease = $false } | ConvertTo-Json -Depth 3
if ($release) {
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/$($release.id)" -Method Patch -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType "application/json; charset=utf-8"
} else {
    $payload = @{ tag_name = $tag; name = $releaseName; body = $body; draft = $false; prerelease = $false } | ConvertTo-Json -Depth 3
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases" -Method Post -Headers $headers -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType "application/json; charset=utf-8"
}

$shaName = Split-Path -Leaf $sha
foreach ($asset in $release.assets) {
    if ($asset.name -eq $zipName -or $asset.name -eq $shaName) {
        Invoke-RestMethod "https://api.github.com/repos/$repo/releases/assets/$($asset.id)" -Method Delete -Headers $headers | Out-Null
        Write-Output "deleted old asset: $($asset.name)"
    }
}

Invoke-RestMethod "https://uploads.github.com/repos/$repo/releases/$($release.id)/assets?name=$zipName" -Method Post -Headers $headers -InFile $zip -ContentType "application/zip" -TimeoutSec 600 | Out-Null
Invoke-RestMethod "https://uploads.github.com/repos/$repo/releases/$($release.id)/assets?name=$shaName" -Method Post -Headers $headers -InFile $sha -ContentType "text/plain" -TimeoutSec 60 | Out-Null

Write-Output "Release: $($release.html_url)"

