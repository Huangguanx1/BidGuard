$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$forbiddenNames = @(".env", "bidguard.db")
$files = Get-ChildItem $root -Recurse -File | Where-Object {
    $_.FullName -notmatch '[\\/](node_modules|dist|data|\.git|\.venv)[\\/]'
}

$badNames = $files | Where-Object { $forbiddenNames -contains $_.Name }
if ($badNames) {
    throw "Forbidden public file found: $($badNames.FullName -join ', ')"
}

$secretPattern = '(sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,})'
$matches = $files | Select-String -Pattern $secretPattern
if ($matches) {
    $matches | Format-Table Path, LineNumber
    throw "Possible API key found"
}

Write-Output "PASS: no forbidden files or common API key patterns found."

