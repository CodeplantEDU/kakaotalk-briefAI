# 제3자 소스 고지

## 카카오톡 로컬 읽기 엔진

- 저장소: https://github.com/sanguneo/nichirin
- 기준 커밋: 6e7838c86064f88695d8b0b24b16b2c6a7a55b1e
- 기준 모듈: kanao 0.31.3, kakaocommon
- 라이선스: MIT. 원문은 THIRD_PARTY_LICENSE.txt 및 vendor/reader/LICENSE에 포함합니다.
- 이전 기반 작업: https://github.com/silver-flight-group/kakaocli
- 원저작권: Copyright (c) 2026 Silver Flight Group, LLC.; Copyright (c) 2026 kanao-cli contributors.

vendor/reader에는 기존에 검수한 읽기 전용 수정본을 포함합니다.
이 프로그램의 어댑터는 읽기 전용 경계를 유지하며 Reader.rooms, messages, attachments를 호출합니다.
새 UI·스케줄러·AI 연결부를 작성했어도 원본 엔진의 저작권은 유지됩니다.
텍스트 전송의 Win32 입력·본문 검증·Enter 제출 방식은 같은 기준 커밋의 windows/kanao/winauto.py를 검토해 적용했습니다. 앱의 직접 전송은 별도 모듈로 제한하고 기존 읽기 worker의 읽기 전용 경계는 유지합니다.
원본 LICENSE·출처 고지를 삭제하거나 전체를 독자 개발 엔진이라고 표시하지 마세요.
vendor/reader/SOURCE.json은 수정본 기준 각 파일 해시와 검증 범위를 기록합니다.

## 실행 의존성

- Node.js 24 LTS: https://nodejs.org/ — 공식 Windows x64 ZIP을 SHA-256으로 확인해 동봉합니다. 원문 LICENSE와 npm의 제3자 고지를 `_internal/runtime/node`에 유지합니다. 버전과 해시는 runtime-lock.json에 고정합니다.
- Microsoft Edge WebView2 Evergreen Bootstrapper: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution — Microsoft 서명을 확인한 bootstrapper를 설치 프로그램에 포함합니다. 런타임이 없는 PC에서 Microsoft 서버로부터 내려받아 설치하며 인터넷이 필요합니다.

- pywin32: https://github.com/mhammond/pywin32 — PSF 계열 라이선스. pip 설치본의 라이선스를 따릅니다.
- Codex CLI: https://github.com/openai/codex — Apache-2.0, 공식 패키지로 별도 설치합니다.
- Gemini CLI: https://github.com/google-gemini/gemini-cli — Apache-2.0, 공식 패키지로 별도 설치합니다.
- Claude Code: https://code.claude.com/ — Anthropic의 소프트웨어·서비스 조건에 따라 별도 설치합니다.

AI 실행 파일, 인증 정보, 대화, DPAPI 키 캐시와 CLI 세션 기록은 소스 묶음에 포함하지 않습니다.
이 고지는 전반적인 법률 검토나 카카오 서비스 약관 적합성 보증을 대신하지 않습니다.

## Windows 테스트 빌드의 동봉 런타임

Python·pywin32·pywebview·pythonnet·clr_loader·cffi·bottle·typing_extensions 등 실제 빌드 의존성의 라이선스 원문과 버전 목록을 설치 폴더 `_internal/licenses`에 포함합니다.
WebView2 SDK 원문은 Microsoft 공식 NuGet 패키지 1.0.3856.49에서 수집합니다. Windows WebView2 런타임 자체는 운영체제의 설치본을 사용합니다.
proxy_tools의 패키지 메타데이터는 MIT로 표시하지만 공식 저장소 LICENSE.txt는 BSD 고지이므로 원문 BSD 고지와 메타데이터를 모두 보존합니다.
배포 저장소는 CodeplantEDU/chatbrief입니다. 신규 앱 소스에 별도의 오픈소스 라이선스를 부여하지 않았습니다. 포함된 제3자 소스에는 원래의 라이선스가 계속 적용됩니다.
