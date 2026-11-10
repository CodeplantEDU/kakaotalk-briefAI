$ErrorActionPreference = 'Stop'
$briefRoot = $PSScriptRoot
$briefSetup = Join-Path $briefRoot 'release/KakaoTalk-BriefAI-0.4.3-rc.1-windows-x64-setup.exe'
$briefPrograms = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs'))
$briefInstall = [IO.Path]::GetFullPath((Join-Path $briefPrograms 'ChatBrief-Test'))
if (-not $briefInstall.StartsWith($briefPrograms + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw '설치 경로 경계 오류' }
if (Test-Path -LiteralPath $briefInstall) { throw '기존 설치가 있어 자동 설치/제거 검사를 중단합니다.' }
$briefPython = Join-Path $briefRoot '.build-venv/Scripts/python.exe'
& $briefPython -B -X utf8 -c 'import runtime_paths; runtime_paths.ensure_runtime()'
if ($LASTEXITCODE -ne 0) { throw '기존 설정 보존 이관 실패' }
$briefData = Join-Path $env:LOCALAPPDATA 'ChatBrief'
$briefCanary = Join-Path $briefData '.installer-test-retained.txt'
[IO.File]::WriteAllText($briefCanary, 'synthetic-retention-check')
$briefState = Join-Path $briefData 'private/state.dpapi'
$briefBeforeHash = if (Test-Path -LiteralPath $briefState) { (Get-FileHash -LiteralPath $briefState -Algorithm SHA256).Hash } else { '' }
try {
    $briefResult = Start-Process -FilePath $briefSetup -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
    if ($briefResult.ExitCode -ne 0) { throw '테스트 설치 실패' }
    if (-not (Test-Path -LiteralPath (Join-Path $briefInstall 'ChatBrief.exe'))) { throw '설치 EXE 없음' }
    if (-not (Test-Path -LiteralPath (Join-Path $briefInstall 'ChatBriefWorker.exe'))) { throw '설치 worker 없음' }
    $briefRegistry = Get-ItemProperty 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/ChatBrief-Test'
    if ($briefRegistry.DisplayVersion -ne '0.4.3-rc.1') { throw '앱 등록 버전 불일치' }
    $briefTempProfile = Join-Path $briefRoot '.build-work/installed-test-profile'
    $env:CHATBRIEF_DATA_DIR = $briefTempProfile
    try {
        $briefResult = Start-Process -FilePath (Join-Path $briefInstall 'ChatBrief.exe') -ArgumentList @('--smoke-test','--port','0') -Wait -PassThru -WindowStyle Hidden
        if ($briefResult.ExitCode -ne 0) { throw '설치본 HTTP 검사 실패' }
        $briefResult = Start-Process -FilePath (Join-Path $briefInstall 'ChatBrief.exe') -ArgumentList @('--ui-smoke-test','--port','0') -Wait -PassThru -WindowStyle Hidden
        if ($briefResult.ExitCode -ne 0) { throw '설치본 네이티브 창 검사 실패' }
    } finally { Remove-Item Env:CHATBRIEF_DATA_DIR -ErrorAction SilentlyContinue }
    # Reinstall the same RC to exercise the upgrade path without touching data.
    $briefResult = Start-Process -FilePath $briefSetup -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
    if ($briefResult.ExitCode -ne 0) { throw '재설치 실패' }
    $briefUninstall = Join-Path $briefInstall 'Uninstall.exe'
    if ((Get-Item -LiteralPath $briefInstall).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '제거 대상이 연결 경로입니다.' }
    $briefResult = Start-Process -FilePath $briefUninstall -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
    if ($briefResult.ExitCode -ne 0) { throw '테스트 제거 실패' }; for ($briefWait=0; $briefWait -lt 100 -and (Test-Path -LiteralPath $briefInstall); $briefWait++) { Start-Sleep -Milliseconds 100 }
    if (Test-Path -LiteralPath (Join-Path $briefInstall 'ChatBrief.exe')) { throw '실행 파일 제거 실패' }
    if (-not (Test-Path -LiteralPath $briefCanary)) { throw '사용자 데이터 보존 실패' }
    $briefAfterHash = if (Test-Path -LiteralPath $briefState) { (Get-FileHash -LiteralPath $briefState -Algorithm SHA256).Hash } else { '' }
    if ($briefBeforeHash -ne $briefAfterHash) { throw '암호화 설정이 변경됐습니다.' }
    # Leave an installed, ready-to-test application for the user.
    $briefResult = Start-Process -FilePath $briefSetup -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
    if ($briefResult.ExitCode -ne 0) { throw '최종 테스트 설치 실패' }
    [pscustomobject]@{ Install='PASS'; InstalledHTTP='PASS'; InstalledNativeWindow='PASS'; Reinstall='PASS'; Uninstall='PASS'; UserDataRetained='PASS'; FinalInstalled=$true } | ConvertTo-Json
} finally {
    if (Test-Path -LiteralPath $briefCanary) { Remove-Item -LiteralPath $briefCanary }
}
