param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$NotesFile = "",
    [string]$Path = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Path) { $Path = Join-Path $root "README.md" }
if (-not (Test-Path -LiteralPath $Path)) { throw "README not found: $Path" }

$text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
$changed = $false

# 1) 当前版本号
$newVer = "**当前版本：v$Version**"
if ($text -notmatch [regex]::Escape($newVer)) {
    $pattern = '\*\*当前版本：v[^*]+\*\*'
    if ($text -match $pattern) {
        $text = [regex]::Replace($text, $pattern, $newVer, 1)
        $changed = $true
    }
}

# 2) 最近更新
if ($text -notmatch "### v$Version\b") {
    $notes = ""
    if ($NotesFile -and (Test-Path -LiteralPath $NotesFile)) {
        $notes = Get-Content -LiteralPath $NotesFile -Raw -Encoding UTF8
    }
    $lines = @()
    $inNotes = $false
    foreach ($line in ($notes -split "`r?`n")) {
        if ($line -match '^##\s*说明') { break }
        if ($line -match '^##\s+') { $inNotes = $true; continue }
        if ($inNotes -and $line.Trim()) { $lines += $line.TrimEnd() }
    }
    $bullets = ($lines -join "`n").Trim()
    if ($bullets) {
        $entry = "### v$Version`n$bullets`n"
        $anchor = "## 最近更新"
        $idx = $text.IndexOf($anchor)
        if ($idx -ge 0) {
            $lineEnd = $text.IndexOf("`n", $idx)
            if ($lineEnd -ge 0) {
                $pos = $lineEnd + 1
                while ($pos -lt $text.Length -and ($text[$pos] -eq "`n" -or $text[$pos] -eq "`r")) { $pos++ }
                $text = $text.Substring(0, $pos) + $entry + "`n" + $text.Substring($pos)
                $changed = $true
            }
        }
    }
}

if ($changed) {
    [IO.File]::WriteAllText($Path, $text, (New-Object Text.UTF8Encoding($false)))
    Write-Output "changed"
} else {
    Write-Output "unchanged"
}
