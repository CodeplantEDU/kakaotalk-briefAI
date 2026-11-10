$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'fonts/PretendardVariable.woff2')) {
    New-Item -ItemType Directory -Path 'fonts' -Force | Out-Null
    Invoke-WebRequest 'https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2' -OutFile 'fonts/PretendardVariable.woff2'
    Invoke-WebRequest 'https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/LICENSE' -OutFile 'fonts/OFL.txt'
}
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw 'Python 3.12 이상을 먼저 설치해 주세요: https://www.python.org/downloads/windows/'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python 환경 생성에 실패했습니다.' }
}
& '.venv/Scripts/python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python 패키지 설치에 실패했습니다.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js LTS를 먼저 설치해 주세요: https://nodejs.org/'
}
$packages = @{ codex = '@openai/codex'; claude = '@anthropic-ai/claude-code'; gemini = '@google/gemini-cli' }
foreach ($cliName in $packages.Keys) {
    if (-not (Get-Command $cliName -ErrorAction SilentlyContinue)) {
        & npm.cmd install -g $packages[$cliName]
        if ($LASTEXITCODE -ne 0) { throw "$cliName 설치에 실패했습니다." }
    }
}
Write-Host '설치 완료. 각 AI CLI에서 본인 계정으로 로그인한 뒤 실행.cmd를 여세요.'
