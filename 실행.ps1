$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$briefPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $briefPython)) {
    $briefPython = Join-Path $env:USERPROFILE '.codex/tools/kakaotalk-readonly/.venv/Scripts/python.exe'
}
if (-not (Test-Path -LiteralPath $briefPython)) { throw '설치.ps1을 먼저 실행해 주세요.' }
try {
    $briefResponse = Invoke-WebRequest 'http://127.0.0.1:8791/api/state' -TimeoutSec 2 -UseBasicParsing
} catch {
    Start-Process -FilePath $briefPython -ArgumentList @('-B', '-X', 'utf8', ('"' + (Join-Path $PSScriptRoot 'app.py') + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
    Start-Sleep -Seconds 2
}
Start-Process 'http://127.0.0.1:8791/'
