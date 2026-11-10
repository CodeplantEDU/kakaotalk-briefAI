Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!ifndef APP_VERSION
  !define APP_VERSION "0.4.4-rc.1"
!endif
Name "KakaoTalk BriefAI"
OutFile "..\release\KakaoTalk-BriefAI-${APP_VERSION}-windows-x64-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\ChatBrief-Test"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "KakaoTalk BriefAI ${APP_VERSION}"
VIProductVersion "0.4.4.1"
VIAddVersionKey /LANG=1042 "ProductName" "KakaoTalk BriefAI"
VIAddVersionKey /LANG=1042 "FileDescription" "KakaoTalk BriefAI 설치 프로그램"
VIAddVersionKey /LANG=1042 "FileVersion" "${APP_VERSION}"
!define MUI_ABORTWARNING
!define MUI_ICON "..\assets\chatbrief.ico"
!define MUI_UNICON "..\assets\chatbrief.ico"
!define MUI_WELCOMEPAGE_TITLE "KakaoTalk BriefAI 설치"
!define MUI_WELCOMEPAGE_TEXT "Windows 64비트용 프로그램입니다.$\r$\n$\r$\nPython과 Node.js가 포함됩니다. 화면 엔진 WebView2가 없으면 인터넷으로 설치합니다.$\r$\n$\r$\n처음 실행하면 사용 안내가 열립니다. 사용할 AI 도구는 앱에서 설치하고 본인 계정으로 로그인합니다.$\r$\n$\r$\n기존 카카오톡 로그인은 유지합니다."
!insertmacro MUI_PAGE_WELCOME
!define MUI_LICENSEPAGE_TEXT_TOP "카카오와 무관한 비공식 프로그램입니다. 이용·면책 고지를 읽고 확인해 주세요."
!define MUI_LICENSEPAGE_CHECKBOX
!insertmacro MUI_PAGE_LICENSE "..\DISCLAIMER.md"
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\ChatBrief.exe"
!define MUI_FINISHPAGE_RUN_TEXT "KakaoTalk BriefAI 실행"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Korean"

Function .onInit
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\ChatBrief-Test"
  System::Call 'kernel32::GetFileAttributesW(w "$INSTDIR") i .r0'
  ${If} $0 <> -1
    IntOp $0 $0 & 0x400
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP "연결된 폴더에는 설치하지 않습니다. 설치 경로를 확인해 주세요." /SD IDOK
      Abort
    ${EndIf}
  ${EndIf}
  IfFileExists "$INSTDIR\*.*" 0 install_path_ready
  ReadINIStr $0 "$INSTDIR\.chatbrief-install.ini" "App" "Id"
  StrCmp $0 "ChatBrief-Test" install_path_ready
    MessageBox MB_OK|MB_ICONSTOP "설치 위치에 다른 파일이 있어 설치를 중단합니다. 기존 파일을 확인해 주세요." /SD IDOK
    Abort
  install_path_ready:
  !include "..\.build-work\uninstall-verify.nsh"
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "64비트 Windows 전용 프로그램입니다." /SD IDOK
    Abort
  ${EndIf}
FunctionEnd

Function CheckWebView
  SetRegView 32
  ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  StrCmp $0 "" webview_machine
  StrCmp $0 "0.0.0.0" webview_machine webview_checked
  webview_machine:
    ReadRegStr $0 HKLM "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  webview_checked:
  SetRegView lastused
FunctionEnd

Function EnsureWebView
  Call CheckWebView
  StrCmp $0 "" webview_install
  StrCmp $0 "0.0.0.0" webview_install webview_ready
  webview_install:
    DetailPrint "화면 엔진 WebView2를 설치합니다. 인터넷 연결이 필요합니다."
    InitPluginsDir
    File "/oname=$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" "..\.build-work\dependencies\MicrosoftEdgeWebview2Setup.exe"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $1
    Call CheckWebView
    StrCmp $0 "" webview_failed
    StrCmp $0 "0.0.0.0" webview_failed webview_ready
  webview_failed:
    SetErrorLevel 1
    MessageBox MB_OK|MB_ICONSTOP "WebView2 설치를 완료하지 못했습니다. 인터넷 연결과 설치 권한을 확인한 뒤 다시 실행해 주세요." /SD IDOK
    Abort
  webview_ready:
FunctionEnd

Section "설치"
  Call EnsureWebView
  SetOutPath "$INSTDIR"
  SetOverwrite on
  ClearErrors
  File /r "..\.build-dist\ChatBrief\*.*"
  IfErrors install_failed
  nsExec::ExecToStack /TIMEOUT=120000 '"$INSTDIR\ChatBriefWorker.exe" --verify-install "${APP_VERSION}"'
  Pop $0
  Pop $1
  StrCmp $0 0 install_verified
  install_failed:
    SetErrorLevel 1
    MessageBox MB_OK|MB_ICONSTOP "프로그램 파일을 모두 갱신하지 못했습니다. KakaoTalk BriefAI를 종료한 뒤 다시 설치해 주세요. 기존 사용자 데이터는 유지됩니다." /SD IDOK
    Abort
  install_verified:
  WriteINIStr "$INSTDIR\.chatbrief-install.ini" "App" "Id" "ChatBrief-Test"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  Delete "$DESKTOP\대화 브리핑 테스트.lnk"
  Delete "$SMPROGRAMS\대화 브리핑 테스트\대화 브리핑.lnk"
  Delete "$SMPROGRAMS\대화 브리핑 테스트\제거.lnk"
  RMDir "$SMPROGRAMS\대화 브리핑 테스트"
  Delete "$DESKTOP\KakaoTalk BriefAI 테스트.lnk"
  Delete "$SMPROGRAMS\KakaoTalk BriefAI 테스트\KakaoTalk BriefAI.lnk"
  Delete "$SMPROGRAMS\KakaoTalk BriefAI 테스트\제거.lnk"
  RMDir "$SMPROGRAMS\KakaoTalk BriefAI 테스트"
  Delete "$INSTDIR\사용자-테스트-안내.md"
  CreateDirectory "$SMPROGRAMS\KakaoTalk BriefAI"
  CreateShortcut "$SMPROGRAMS\KakaoTalk BriefAI\KakaoTalk BriefAI.lnk" "$INSTDIR\ChatBrief.exe"
  CreateShortcut "$SMPROGRAMS\KakaoTalk BriefAI\제거.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\KakaoTalk BriefAI.lnk" "$INSTDIR\ChatBrief.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatBrief-Test" "DisplayName" "KakaoTalk BriefAI"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatBrief-Test" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatBrief-Test" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatBrief-Test" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatBrief-Test" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatBrief-Test" "NoRepair" 1
SectionEnd

Function un.onInit
  SetShellVarContext current
  GetFullPathName $0 "$INSTDIR"
  GetFullPathName $1 "$LOCALAPPDATA\Programs\ChatBrief-Test"
  StrCmp $0 $1 +3
    MessageBox MB_OK|MB_ICONSTOP "설치 경로가 일치하지 않아 제거를 중단합니다." /SD IDOK
    Abort
  ReadINIStr $0 "$INSTDIR\.chatbrief-install.ini" "App" "Id"
  StrCmp $0 "ChatBrief-Test" +3
    MessageBox MB_OK|MB_ICONSTOP "설치 확인 파일이 없어 제거를 중단합니다." /SD IDOK
    Abort
  System::Call 'kernel32::GetFileAttributesW(w "$INSTDIR") i .r0'
  IntOp $0 $0 & 0x400
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "연결된 설치 폴더는 제거하지 않습니다." /SD IDOK
    Abort
  ${EndIf}
  System::Call 'kernel32::GetFileAttributesW(w "$INSTDIR\_internal") i .r0'
  ${If} $0 <> -1
    IntOp $0 $0 & 0x400
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP "연결된 내부 폴더는 제거하지 않습니다." /SD IDOK
      Abort
    ${EndIf}
  ${EndIf}
  !include "..\.build-work\uninstall-verify.nsh"
FunctionEnd

Section "Uninstall"
  Delete "$DESKTOP\KakaoTalk BriefAI.lnk"
  Delete "$SMPROGRAMS\KakaoTalk BriefAI\KakaoTalk BriefAI.lnk"
  Delete "$SMPROGRAMS\KakaoTalk BriefAI\제거.lnk"
  RMDir "$SMPROGRAMS\KakaoTalk BriefAI"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatBrief-Test"
  !include "..\.build-work\uninstall-files.nsh"
  Delete "$INSTDIR\.chatbrief-install.ini"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  ; User data and encrypted keys under LOCALAPPDATA\ChatBrief are always retained.
SectionEnd
