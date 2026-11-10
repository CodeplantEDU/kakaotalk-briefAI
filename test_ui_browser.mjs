/**
 * Run only against test_ui_fixture.py through the documented Browser Tab API.
 * This module is imported by the Node REPL browser session, never standalone.
 * It performs no real installation, account login, Kakao access, or AI request.
 */
const ensure = (value, message) => { if (!value) throw new Error(message); };

export async function runUiBrowserChecks(tab) {
  ensure((await tab.url()) === 'http://127.0.0.1:8855/', 'Refusing any non-fixture page');
  const passed = [];
  const ui = tab.playwright;

  await ui.locator('#home-page').waitFor({state: 'visible'});
  passed.push('홈 첫 화면');

  await ui.locator('#nav-settings').click();
  const aiSelect = ui.locator('.ai-settings .select-trigger');
  await aiSelect.press('ArrowDown');
  await ui.locator('.ai-settings .select-option[data-value="codex"]').press('ArrowDown');
  await ui.locator('.ai-settings .select-option[data-value="claude"]').press('Enter');
  ensure((await aiSelect.innerText()) === 'Claude', 'Keyboard AI selection failed');
  await aiSelect.press('ArrowDown');
  await ui.locator('.ai-settings .select-option[data-value="claude"]').press('ArrowUp');
  await ui.locator('.ai-settings .select-option[data-value="codex"]').press('Enter');
  ensure((await aiSelect.innerText()) === 'Codex', 'Keyboard AI selection reset failed');
  passed.push('커스텀 AI 메뉴 키보드 선택');

  await ui.locator('#nav-settings').click();
  await ui.locator('#provider-install-list .provider-install-card').first().waitFor({state: 'visible'});
  const codexCard = ui.locator('.provider-install-card').filter({hasText: 'Codex'});
  const install = codexCard.getByRole('button', {name: '설치하기', exact: true});
  if (await install.count()) await install.click();
  await codexCard.getByText('설치됨', {exact: true}).waitFor({state: 'visible', timeoutMs: 10000});
  await codexCard.locator('.login-guide summary').click();
  ensure((await codexCard.locator('.login-command code').innerText()).includes('C:/Fixture Node/node.exe'), 'Server-provided wrapper login command was not shown');
  await codexCard.getByRole('button', {name: '연결 테스트', exact: true}).click();
  await codexCard.getByText('가상 메시지 응답 확인 완료', {exact: true}).waitFor({state: 'visible'});
  passed.push('설정의 모의 설치 job 및 가상 연결 테스트');

  await ui.locator('#nav-batch').click();
  await ui.locator('#search').fill('');
  await ui.locator('#refresh').click();
  await ui.getByText('300개 채팅방 · 100개 표시',{exact:true}).waitFor({state:'visible'});
  ensure((await ui.locator('#rooms .room').count()) === 100, 'Initial room DOM must be bounded');
  await ui.locator('#search').fill('테스트 채팅방 00');
  await ui.locator('#select-all').click();
  ensure((await ui.locator('#selectedCount').innerText()) === '9개 선택', 'Search-result select all failed');
  await ui.locator('#save-selection').click();
  await ui.getByText('9개 채팅방 선택을 저장했습니다.', {exact: true}).waitFor({state: 'visible'});
  passed.push('목록 100개 표시와 검색 결과 전체 선택');

  await ui.locator('#nav-schedule').click();
  await ui.locator('#schedule-search').fill('테스트 채팅방 010');
  await ui.locator('#schedule-room-list input').setChecked(true);
  await ui.locator('#save').click();
  await ui.getByText('예약 설정을 저장했습니다.', {exact: true}).waitFor({state: 'visible'});
  ensure((await ui.locator('#reservation-rooms .selected-chip').count()) === 1, 'Reservation target count failed');
  await ui.locator('#nav-batch').click();
  ensure((await ui.locator('#selectedCount').innerText()) === '9개 선택', 'Reservation target changed manual selection');
  passed.push('일반·예약 채팅방 선택 독립');

  await ui.locator('#summary-start').fill('2026-11-01');
  await ui.locator('#summary-end').fill('2026-11-10');
  await ui.locator('#summarize-range').click();
  await ui.getByText('AI 요약을 저장했습니다.', {exact: true}).waitFor({state: 'visible'});
  ensure((await ui.locator('#batch-reports .report').count()) === 9, 'Date-range summary did not return selected rooms');
  ensure((await ui.locator('#batch-reports .report-sub').first().innerText()).includes('기간 대화'), 'Date-range scope label failed');
  await ui.locator('#nav-home').click();
  ensure((await ui.locator('#home-feed .feed-card').count()) >= 9, 'Briefing history missing from home');
  passed.push('기간 요약과 홈 브리핑 누적');

  await ui.locator('#home-feed .feed-card').first().getByRole('button', {name: '요약 보기', exact: true}).click();
  await ui.locator('.chat-row').first().waitFor({state: 'visible'});
  await ui.locator('#summary-side').waitFor({state: 'visible'});
  ensure((await ui.locator('.chat-row').count()) === 2, 'Chat bubble rendering failed');
  const separator = ui.locator('#summary-resizer');
  if (await separator.isVisible()) {
    const width = Number(await separator.getAttribute('aria-valuenow'));
    await separator.press('ArrowLeft');
    ensure(Number(await separator.getAttribute('aria-valuenow')) >= width, 'Keyboard resizing failed');
    passed.push('대화·요약 나란히 표시 및 키보드 폭 조절');
  } else {
    passed.push('대화·요약 표시(좁은 화면: 세로 배치)');
  }

  await ui.locator('#chat-generate').click();
  await ui.getByText('답장 초안을 만들었습니다. 내용을 확인하고 수정해 주세요.', {exact: true}).waitFor({state: 'visible'});
  ensure((await ui.locator('#chat-draft').evaluate(el => el.value)).includes('검수용 가상 초안'), 'Contextual draft did not render');
  ensure((await ui.locator('#reply-style-status').innerText()).includes('메시지 샘플이 부족합니다'), 'Insufficient style sample guidance missing');
  passed.push('대화 아래 가상 답장 초안');

  await ui.locator('#nav-todos').click();
  await ui.locator('#todo-title').fill('가상 검수 할 일');
  await ui.locator('#todo-due').fill('2026-11-11');
  await ui.getByRole('button', {name: '할 일 추가', exact: true}).click();
  const task = ui.locator('.todo-item').filter({hasText: '가상 검수 할 일'}).last();
  await task.waitFor({state: 'visible'});
  await task.getByRole('checkbox').setChecked(true);
  await ui.locator('.todo-item.done').filter({hasText: '가상 검수 할 일'}).last().waitFor({state: 'visible'});
  passed.push('할 일 직접 추가·완료');

  await ui.locator('#theme-dark').click();
  ensure((await ui.locator('#theme-dark').getAttribute('aria-pressed')) === 'true', 'Dark theme selection failed');
  await ui.locator('#theme-light').click();
  ensure((await ui.locator('#theme-light').getAttribute('aria-pressed')) === 'true', 'Light theme selection failed');
  passed.push('라이트·다크 선택');
  await ui.locator('#nav-settings').click();
  return {ok: true, fixtureOnly: true, checks: passed};
}

export async function runDirectSendBrowserChecks(tab) {
  ensure((await tab.url()) === 'http://127.0.0.1:8855/', 'Refusing any non-fixture send test');
  const ui=tab.playwright,passed=[];
  await ui.locator('#nav-summary').click();await ui.locator('#chat-refresh-list').click();await ui.locator('#chat-rooms .conversation-room').first().waitFor({state:'visible'});
  await ui.locator('#chat-search').fill('테스트 채팅방 001');await ui.getByRole('button',{name:'테스트 채팅방 001 대화 보기',exact:true}).click();await ui.locator('.chat-row').first().waitFor({state:'visible'});
  const draft=ui.locator('#chat-draft'),send=ui.locator('#chat-send');ensure((await ui.locator('#send-confirm').count())===0,'Obsolete confirmation dialog remains');
  const sent=async body=>ui.locator('.chat-row.mine .bubble p').filter({hasText:body}).last();
  const body='수정한 가상 전송 본문입니다.';await draft.fill(body);await send.click();await ui.locator('#send-outcome[data-delivery="submitted"]').waitFor({state:'visible'});await sent(body).waitFor({state:'visible'});ensure((await draft.evaluate(el=>el.value))==='','Successful send did not clear the unchanged body');ensure((await ui.locator('#send-confirm').count())===0,'Click send opened confirmation');passed.push('버튼 전송·팝업 없음·성공 응답 뒤 자동 대화 갱신·본문 비우기');
  await draft.fill('Shift+Enter 줄바꿈');await draft.press('Shift+Enter');ensure((await draft.evaluate(el=>el.value))==='Shift+Enter 줄바꿈\n','Shift+Enter did not insert a newline');
  const enterBody='Enter 키로 보내는 가상 메시지';await draft.fill(enterBody);await draft.press('Enter');await draft.press('Enter');await sent(enterBody).waitFor({state:'visible'});await draft.waitFor({state:'visible'});ensure((await draft.evaluate(el=>el.value))==='','Enter send did not clear its submitted body');ensure(await sent(enterBody).count()===1,'Repeated Enter submitted the same body more than once');passed.push('Enter 전송·Shift+Enter 줄바꿈·연속 Enter 중복 차단');
  const uncertain='[unknown] 가상 결과 불확실 검수';await draft.fill(uncertain);await send.click();await ui.locator('#send-outcome[data-delivery="unknown"]').waitFor({state:'visible'});ensure((await draft.evaluate(el=>el.value))===uncertain,'Unknown result discarded the draft');ensure(!(await send.isEnabled()),'Unknown result allowed an unreviewed retry');await ui.getByRole('button',{name:'카카오톡에서 확인했어요'}).click();ensure(await send.isEnabled(),'Manual unknown acknowledgement did not unlock send');passed.push('불확실 결과 자동 재시도 차단·초안 보존');
  const rejected='[not_delivered] 가상 거부 검수';await draft.fill(rejected);await send.click();await ui.locator('#send-outcome[data-delivery="not_delivered"]').waitFor({state:'visible'});ensure((await draft.evaluate(el=>el.value))===rejected,'Rejected result discarded the draft');passed.push('미전달 결과 초안 보존');
  const hint='[hint] 고정 입력 안내 문구 교체 검수';await draft.fill(hint);await send.click();await ui.locator('#send-outcome[data-delivery="submitted"]').waitFor({state:'visible'});await sent(hint).waitFor({state:'visible'});ensure((await draft.evaluate(el=>el.value))==='','Fixed placeholder replacement was not submitted');passed.push('서버가 요구한 고정 입력 안내 문구만 replaceHint=true 처리');
  const tooLong='가'.repeat(2001);await draft.fill(tooLong);await send.click();await ui.getByText('직접 전송은 2,000자 이하의 본문만 지원합니다. 초안은 그대로 유지했습니다.',{exact:true}).waitFor({state:'visible'});ensure((await draft.evaluate(el=>el.value))===tooLong,'Oversize validation truncated the body');ensure((await ui.locator('#send-confirm').count())===0,'Oversize text opened confirmation');passed.push('2,000자 제한·미리보기 팝업 제거');
  return {ok:true,fixtureOnly:true,actualKakaoSend:false,checks:passed};
}
export async function runSendResponseFailureCheck(tab) {
  ensure((await tab.url()) === 'http://127.0.0.1:8855/', 'Refusing any non-fixture send response test');
  const ui=tab.playwright;await ui.locator('#nav-summary').click();await ui.locator('#chat-refresh-list').click();await ui.locator('#chat-rooms .conversation-room').first().waitFor({state:'visible'});await ui.locator('#chat-search').fill('테스트 채팅방 001');await ui.getByRole('button',{name:'테스트 채팅방 001 대화 보기',exact:true}).click();await ui.locator('.chat-row').first().waitFor({state:'visible'});
  const body='[transport] 가상 응답 유실 검수';await ui.locator('#chat-draft').fill(body);await ui.locator('#chat-send').click();await ui.locator('#send-outcome[data-delivery="unknown"]').waitFor({state:'visible'});ensure(!(await ui.locator('#chat-send').isEnabled()),'Unreadable acknowledgement allowed an unreviewed retry');ensure((await ui.locator('#chat-draft').evaluate(el=>el.value))===body,'Unreadable acknowledgement discarded the draft');ensure((await ui.locator('#send-outcome').innerText()).includes('응답을 받지 못해'),'Unreadable acknowledgement did not use the uncertain transport path');ensure((await ui.locator('#send-confirm').count())===0,'Send response failure opened a confirmation');return {ok:true,fixtureOnly:true,actualKakaoSend:false,check:'제출 응답 유실은 unknown 처리·자동 재시도 차단·초안 보존'};
}export async function runSelectionIndependenceChecks(tab){
 ensure((await tab.url())==='http://127.0.0.1:8855/','Fixture only');const ui=tab.playwright,passed=[];
 await ui.locator('#nav-batch').click();await ui.locator('#clear-all').click();
 ensure(!(await ui.locator('#summarize-all').isEnabled()),'Zero selection all enabled');ensure(!(await ui.locator('#summarize-today').isEnabled()),'Zero selection today enabled');ensure(!(await ui.locator('#summarize-range').isEnabled()),'Zero selection range enabled');passed.push('선택 0개 모든 여러방 실행 비활성');
 await ui.locator('#nav-summary').click();await ui.locator('#chat-search').fill('테스트 채팅방 001');await ui.getByRole('button',{name:'테스트 채팅방 001 대화 보기',exact:true}).click();await ui.locator('.chat-row').first().waitFor({state:'visible'});
 ensure((await ui.locator('#chat-rooms input[type=checkbox]').count())===0,'Conversation list has selection checkbox');
 await ui.locator('#nav-batch').click();ensure((await ui.locator('#selectedCount').innerText())==='0개 선택','Opening room added to batch');passed.push('대화 열기와 여러 방 체크 독립');
 await ui.locator('#nav-schedule').click();await ui.locator('#time').fill('08:25');
 await ui.locator('#nav-summary').click();await ui.locator('#summarize-this-room').click();await ui.getByText('테스트 채팅방 001 요약을 저장했습니다.',{exact:true}).waitFor({state:'visible'});ensure((await ui.locator('#reports .report h3').innerText())==='테스트 채팅방 001','Single room summary wrong target');await ui.locator('#nav-batch').click();ensure((await ui.locator('#selectedCount').innerText())==='0개 선택','Single summary added batch selection');await ui.locator('#nav-schedule').click();ensure((await ui.locator('#schedule-time').innerText())==='09:00','Single summary silently saved schedule');passed.push('선택 없이 현재방 요약·예약 미저장값 보존');
 await ui.locator('#nav-summary').click();await ui.locator('#chat-draft').fill('아직 저장하지 않은 방별 답장');await ui.locator('#chat-search').fill('테스트 채팅방 002');await ui.getByRole('button',{name:'테스트 채팅방 002 대화 보기',exact:true}).click();await ui.locator('#chat-title').getByText('테스트 채팅방 002',{exact:true}).waitFor({state:'visible'});await ui.locator('#chat-search').fill('테스트 채팅방 001');await ui.getByRole('button',{name:'테스트 채팅방 001 대화 보기',exact:true}).click();ensure((await ui.locator('#chat-draft').evaluate(e=>e.value))==='아직 저장하지 않은 방별 답장','Draft lost on room switch');passed.push('방 이동 후 미저장 초안 복원');
 await ui.locator('#nav-batch').click();await ui.locator('#search').fill('테스트 채팅방 002');await ui.locator('#rooms input').setChecked(true);await ui.locator('#summarize-today').click();await ui.getByText('AI 요약을 저장했습니다.',{exact:true}).waitFor({state:'visible'});ensure((await ui.locator('#batch-reports .report').count())===1,'Batch wrong result count');ensure((await ui.locator('#batch-reports h3').innerText())==='테스트 채팅방 002','Active conversation contaminated batch target');await ui.locator('#clear-all').click();ensure((await ui.locator('#batch-reports h3').innerText())==='테스트 채팅방 002','Deselect erased summary');passed.push('현재방과 다른 체크대상만 요약·해제 후 결과 보존');
 return {ok:true,fixtureOnly:true,checks:passed};
}

export async function runTutorialBrowserChecks(tab) {
  ensure((await tab.url()) === 'http://127.0.0.1:8855/', 'Refusing any non-fixture page');
  const ui = tab.playwright;
  const guide=ui.locator('#tutorial-guide'),next=ui.locator('#tutorial-next'),passed=[];
  const stage=async(n,title)=>{await ui.locator('#tutorial-step-label').waitFor({state:'visible'});ensure((await ui.locator('#tutorial-step-label').innerText()).startsWith(`${n} / 8`),`Expected tutorial step ${n}`);ensure((await ui.locator('#tutorial-title').innerText())===title,`Unexpected tutorial title at ${n}`);};
  const done=async()=>ensure(await next.isEnabled(),'Step completion was not recognized');
  await guide.waitFor({state:'visible'});await stage(1,'AI 연결 확인');
  await ui.locator('#test-provider').click();await ui.getByText('AI 연결을 확인했습니다.',{exact:true}).waitFor({state:'visible'});await done();await next.click();passed.push('최초 표시·AI 연결 성공');
  await stage(2,'채팅방 검색하고 열기');await ui.locator('#chat-refresh-list').click();await ui.locator('#chat-search').fill('테스트 채팅방 001');await ui.getByRole('button',{name:'테스트 채팅방 001 대화 보기',exact:true}).click();await ui.locator('.chat-row').first().waitFor({state:'visible'});await done();await next.click();passed.push('대화 목록 검색·실제 방 열기');
  await stage(3,'이 방 요약하기');await ui.locator('#room-scope').selectOption('all');await ui.locator('#summarize-this-room').click();ensure(!(await next.isEnabled()),'Failed summary marked tutorial complete');await ui.locator('#summarize-this-room').click();await done();await next.click();passed.push('단일 방 요약 오류 실패·재시도 성공');
  await stage(4,'여러 방 요약하기');await ui.locator('#refresh').click();await ui.locator('#search').fill('테스트 채팅방 001');await ui.locator('#select-all').click();await ui.locator('#summarize-today').click();await done();await next.click();passed.push('전체 선택 이벤트·여러 방 요약 성공');
  await stage(5,'내 말투 답장 초안');await ui.locator('#chat-generate').click();await ui.getByText('답장 초안을 만들었습니다. 내용을 확인하고 수정해 주세요.',{exact:true}).waitFor({state:'visible'});await ui.locator('#chat-draft').fill('검수용으로 직접 고친 가상 답장입니다.');await ui.locator('#chat-save').click();await done();await next.click();passed.push('AI 모의 초안·직접 수정·저장');
  await stage(6,'전송 방법 익히기');ensure((await ui.locator('#send-confirm').count())===0,'Tutorial added a send popup');await ui.locator('#tutorial-confirm-step').click();await done();await next.click();passed.push('튜토리얼 전송방법 확인은 실제 발송 없이 완료');
  await stage(7,'할 일 추가하기');await ui.locator('#todo-title').fill('튜토리얼 검수용 가상 할 일');await ui.getByRole('button',{name:'할 일 추가',exact:true}).click();await ui.locator('.todo-item').filter({hasText:'튜토리얼 검수용 가상 할 일'}).waitFor({state:'visible'});await done();await next.click();passed.push('할 일 직접 추가');
  await stage(8,'예약 대상과 시간 저장');const enabledBefore=await ui.locator('#enabled').evaluate(el=>el.checked),savedTime=await ui.locator('#time').evaluate(el=>el.value);await ui.locator('#schedule-refresh').click();await ui.locator('#schedule-select-all').click();await ui.locator('#save').click();await ui.getByText('예약 설정을 저장했습니다.',{exact:true}).waitFor({state:'visible'});await done();ensure((await ui.locator('#enabled').evaluate(el=>el.checked))===enabledBefore,'Tutorial changed the daily-check toggle');ensure((await ui.locator('#time').evaluate(el=>el.value))===savedTime,'Tutorial changed the existing time without user action');passed.push('예약 전체 선택·기본 시간 확인 후 명시 저장·자동 켜기 없음');
  await ui.locator('#tutorial-finish').click();await guide.waitFor({state:'hidden'});await tab.reload();await guide.waitFor({state:'hidden'});passed.push('완료 상태 서버 저장·새로고침 후 자동 재표시 안 함');
  await ui.locator('#nav-settings').click();await ui.locator('#tutorial-replay').click();await stage(1,'AI 연결 확인');await ui.locator('#tutorial-skip').click();await done();await next.click();await stage(2,'채팅방 검색하고 열기');await ui.locator('#tutorial-later').click();await guide.waitFor({state:'hidden'});await tab.reload();await guide.waitFor({state:'hidden'});passed.push('설정 다시 보기·건너뛰기·나중에 보기 상태 저장');
  await ui.locator('#nav-settings').click();await ui.locator('#tutorial-replay').click();await stage(1,'AI 연결 확인');await ui.locator('#tutorial-skip').click();await ui.locator('#tutorial-next').press('Enter');await stage(2,'채팅방 검색하고 열기');await ui.locator('#tutorial-prev').press('Enter');await stage(1,'AI 연결 확인');passed.push('키보드 이전·다음');
  return {ok:true,fixtureOnly:true,actualAI:false,actualKakaoRead:false,actualSend:false,checks:passed};
}

export async function runQuietHistoryRefreshBrowserChecks(tab){
  ensure((await tab.url())==='http://127.0.0.1:8855/','Fixture only');const ui=tab.playwright,passed=[];
  await ui.locator('#nav-summary').click();await ui.locator('#chat-refresh-list').click();await ui.locator('#chat-search').fill('300');await ui.getByRole('button',{name:'테스트 채팅방 300 대화 보기',exact:true}).click();await ui.locator('.chat-row').first().waitFor({state:'visible'});
  await ui.locator('.load-earlier').click();await ui.locator('.chat-row').filter({hasText:'이전 페이지의 첫 대화입니다.'}).waitFor({state:'visible'});ensure((await ui.locator('.load-earlier').count())===0,'Fixture older page did not finish pagination');
  const draft='주기 갱신 중 보존할 미저장 초안';await ui.locator('#chat-draft').fill(draft);const container=ui.locator('#chat-messages');await container.evaluate(el=>{el.scrollTop=0});
  await new Promise(resolve=>setTimeout(resolve,5400));
  await ui.locator('.chat-row').filter({hasText:'자동 새로고침으로 도착한 가상 메시지입니다.'}).waitFor({state:'visible',timeoutMs:5000});
  ensure((await ui.locator('.chat-row').filter({hasText:'이전 페이지의 첫 대화입니다.'}).count())===1,'Quiet refresh dropped fully loaded older messages');ensure((await ui.locator('#chat-draft').evaluate(el=>el.value))===draft,'Quiet refresh changed the unsaved draft');ensure((await container.evaluate(el=>el.scrollTop))<=20,'Quiet refresh moved the user scroll position');passed.push('5초 조용한 갱신·새 메시지 반영·전체 페이지/초안/스크롤 보존');
  return {ok:true,fixtureOnly:true,checks:passed};
}
