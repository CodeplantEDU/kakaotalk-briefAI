"""Update only this app's portable source and central catalog records."""
import json
import shutil
from pathlib import Path
from package_source import BASE, source_files

REPO = Path.home() / 'Desktop/AI_Program/10. 스킬/작업본/codeplant-skills-sync-20261025'
BUNDLE = REPO / 'external/kakao-brief-local'
ENTRY = {'id': 'kakao-brief-local', 'category': 'external', 'path': 'external/kakao-brief-local',
         'description': 'Enter 직접 전송·대화 자동 갱신·8단계 안내·내 말투 답장과 대화 요약·예약 Windows 프로그램',
         'source': {'kind': 'user-requested-local-application', 'version': '0.4.2-rc.1',
                    'public_repository': 'https://github.com/CodeplantEDU/chatbrief',
                    'reader_repository': 'https://github.com/sanguneo/nichirin',
                    'reader_commit': '6e7838c86064f88695d8b0b24b16b2c6a7a55b1e',
                    'reader_license': 'MIT', 'font_repository': 'https://github.com/orioncactus/pretendard',
                    'font_version': '1.3.9', 'font_license': 'OFL-1.1', 'last_checked': '2026-11-10',
                    'snapshot_scope': 'portable source and licenses only; no conversations, credentials, keys, binaries, settings or CLI session history'},
         'install_method': 'application',
         'status': 'GitHub 공개 프리릴리스용 Windows RC. Enter·직접 전송에 추가 확인창 없음, 열린 대화 자동 갱신, 체험 안내·Node.js 동봉·AI CLI 선택 설치·같은 방 본인 말투 참고 답장. 실제 발송·AI 응답 품질·WebView2 신규 설치는 미검증.'}


def main():
    BUNDLE.mkdir(parents=True, exist_ok=True)
    for source in source_files():
        if source.suffix.lower() in {'.woff2', '.png', '.ico'}:
            continue  # Font bytes ship in the local ZIP; registry keeps the OFL and installer.
        target = BUNDLE / 'source' / source.relative_to(BASE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    readme = (BASE / 'README.md').read_text(encoding='utf-8')
    readme = readme.replace('](TESTING.md)', '](source/TESTING.md)').replace('](RELEASE-CHECKLIST.md)', '](source/RELEASE-CHECKLIST.md)')
    (BUNDLE / 'README.md').write_text(readme, encoding='utf-8')
    (BUNDLE / 'registry-entry.json').write_text(json.dumps(ENTRY, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    catalog_path = REPO / 'catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    existing = next((entry for entry in catalog['packages'] if entry['id'] == ENTRY['id']), None)
    if existing:
        existing.update(ENTRY)
    else:
        catalog['packages'].append(ENTRY)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    guides_path = REPO / 'skill-library-guides.json'
    guides = json.loads(guides_path.read_text(encoding='utf-8'))
    guides['bundles'][ENTRY['id']] = {'title': '카카오톡 대화 브리핑',
        'use': '로컬 화면에서 대화·첨부·AI 요약·할 일·초안을 관리하고, Enter 또는 직접 전송으로 열린 카카오톡 방에 Win32로 전송하고 대화를 자동 갱신합니다. 예약 대상은 별도 선택합니다. Gemini 계정 연결은 미확인입니다.',
        'example': '대화 브리핑을 실행하고 예약 관리에서 별도의 채팅방을 선택해 오전 9시 요약을 설정해줘.'}
    guides_path.write_text(json.dumps(guides, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for relative, header, entry in [
        ('README.md', '| 메인 | 역할 |\n|---|---|\n', '| [kakao-brief-local](external/kakao-brief-local/README.md) | 카카오톡 로컬 대화·요약·예약·할 일 프로그램 |\n'),
        ('external/README.md', '| 메인 | 역할 | 저장된 직접 진입점 |\n|---|---|---|\n', '| [kakao-brief-local](kakao-brief-local/README.md) | 카카오톡 대화 브리핑 로컬 프로그램 | 0 |\n')]:
        path = REPO / relative
        body = path.read_text(encoding='utf-8')
        if 'kakao-brief-local/README.md' not in body:
            assert header in body
            path.write_text(body.replace(header, header + entry, 1), encoding='utf-8')
    path = REPO / 'docs/SKILL-LIBRARY.md'
    body = path.read_text(encoding='utf-8')
    heading = '## 2026-11-10 카카오톡 대화 브리핑 0.4.2-rc.1 직접 전송과 대화 자동 갱신'
    if heading not in body:
        path.write_text(body.rstrip() + '\n\n' + heading + '\n\n[kakao-brief-local](../external/kakao-brief-local/README.md)에 Enter·버튼 직접 전송과 열린 대화 자동 갱신을 반영했습니다. 전송 확인 팝업은 제거하며 기존 대상 검증·초안 보존·중복 방지를 유지합니다. 실제 화면 체험 안내는 실제 발송을 요구하지 않습니다. 소스와 MIT·OFL 고지를 보관하며 대화·설정·키·바이너리는 제외합니다. 실제 메시지 전송·예약 시간 도달·재부팅은 사용자 시험 대상으로 남깁니다. 공개 저장소는 CodeplantEDU/chatbrief이며 설치 EXE와 소스는 프리릴리스로 배포합니다.\n', encoding='utf-8')
    print('Registered portable source and metadata; private runtime data excluded')


if __name__ == '__main__':
    main()
