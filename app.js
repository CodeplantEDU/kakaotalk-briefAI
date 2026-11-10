let state, token, rooms = [], chosen = new Map(), tab = 'summary', dirty = false, providerList = [], scheduled = new Map();
let activeRoom=null, historyMessages=[], historyAttachments=[], historyBefore=null;
const historyCache=new Map();let queuedHistoryRead=null;
let roomLimit=100, scheduleLimit=100, feedLimit=20, historyRequestId=0, aiRequestRunning=false;
let setupState=null, setupPoll=null;
let currentPage="home", batchResultIds=[], batchHasRun=false, batchResultMeta="", batchSelectionKey="", chatRoomLimit=100, roomsLoaded=false, roomsLoading=false;
const connectionChecks=new Map();
let sendPreviewRequestId=0, sendPreparing=false, sendInFlight=false, quietHistoryBusy=false, draftComposing=false;
const sendOutcomes=new Map(), sessionDrafts=new Map();
const $ = id => document.getElementById(id);
const emptyReport = $('reports').firstElementChild.cloneNode(true);
const text = (tag, content, cls) => { const e = document.createElement(tag); e.textContent = content; if (cls) e.className = cls; return e; };
const errors = {WORKER_FAILED_OR_RESOURCE_LIMIT:'대화 읽기를 완료하지 못했습니다. 프로그램을 다시 실행한 뒤 채팅방 수를 줄여 시도해 주세요.',WORKER_EXECUTABLE_MISSING:'대화 읽기 파일을 찾지 못했습니다. 프로그램을 다시 설치해 주세요.',KEY_UNAVAILABLE:'이 방은 카카오톡에서 한 번 열어 키를 준비해 주세요.',BUSY:'다른 읽기가 진행 중입니다. 잠시 뒤 다시 시도해 주세요.',CHAT_NOT_FOUND:'채팅방을 찾을 수 없습니다.',LOCAL_READ_TIMEOUT:'읽기 시간이 초과되었습니다.',COLLECTION_LIMIT:'수집 시간 한도에 도달했습니다. 채팅방 수를 줄여 다시 확인해 주세요. 예약 확인 위치는 유지됩니다.'};
function notice(s) { $('notice').textContent = s; }
async function api(path, data = {}) { const res = await fetch('/api/' + path, {method:'POST', headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(data)}); const out = await res.json(); if (!res.ok || out.error) throw Error(errors[out.error] || out.error || '확인하지 못했습니다.'); return out; }
function renderRooms() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const display = rooms.filter(r => r.title.toLocaleLowerCase().includes(query));
  $('rooms').replaceChildren();
  for (const r of display.slice(0,roomLimit)) {
    const label = text('div','', 'room' + (chosen.has(r.id) ? ' chosen' : ''));
    const input = document.createElement('input'); input.type = 'checkbox'; input.checked = chosen.has(r.id); input.setAttribute('aria-label', r.title + ' 선택');
    input.disabled=aiRequestRunning; input.onchange = () => { if (input.checked) {chosen.set(r.id, {id:r.id,title:r.title});tutorialBatchSelections.add(r.id);tutorialAction('batch-selected',tutorialBegin('batch-selected'),{roomId:r.id});} else chosen.delete(r.id); dirty = true; renderRooms(); notice('요약 대상을 바꿨습니다. 저장하지 않아도 바로 요약할 수 있습니다.'); };
    const info = text('label','', 'room-info');input.id='batch-room-'+r.id;info.htmlFor=input.id; info.append(text('span',r.title,'room-title'),text('span', `${r.memberCount ? r.memberCount+'명 · ':''}${r.readable ? '읽기 준비됨' : '처음 읽을 때 연결 확인'}`, 'room-meta')); label.append(input,info); $('rooms').append(label);
  }
  if (!display.length) $('rooms').append(text('div',rooms.length ? '검색 결과가 없습니다.' : '새로고침으로 채팅방을 불러와 주세요.','empty-small'));
  if(display.length>roomLimit){const more=text('button',`다음 ${Math.min(100,display.length-roomLimit)}개 보기`,'list-more');more.onclick=()=>{roomLimit+=100;renderRooms();};$('rooms').append(more);}
  $('roomCount').textContent = `${display.length}개 채팅방${display.length>roomLimit?' · '+roomLimit+'개 표시':''}`;
  $('selectedCount').textContent = `${chosen.size}개 선택`;
  renderSelected();renderConversationRooms();updateSummaryControls();
}
function renderSelected(){
  $('selected-rooms').replaceChildren();
  for(const r of [...chosen.values()].slice(0,50)){
    const chip=text('div','','selected-chip');chip.append(text('span',r.title));
    const remove=text('button','×');remove.setAttribute('aria-label',r.title+' 선택 해제');remove.onclick=()=>{chosen.delete(r.id);dirty=true;renderRooms();notice('요약 대상에서 제외했습니다.');};chip.append(remove);$('selected-rooms').append(chip);

  }
  if(chosen.size>50)$('selected-rooms').append(text('p',`외 ${chosen.size-50}개 채팅방`,'selection-overflow'));
  renderScheduled();
  if(!chosen.size){$('selected-rooms').append(text('p','채팅방을 선택하면 여기에 모입니다.'));}

}
function renderSchedule(){
  $('schedule-status').textContent=state.enabled&&(state.scheduleSelected||[]).length?'예약 켜짐':'예약 꺼짐';$('schedule-time').textContent=state.time;
  $('next-run').textContent=state.nextRun?'다음 확인 '+new Date(state.nextRun).toLocaleString('ko-KR'):'예약을 켜고 저장하면 다음 확인 시간이 표시됩니다.';
}
function page(name){currentPage=name;const pages={home:'home-page',summary:'summary-page',batch:'batch-page',schedule:'reservation-page',todos:'todos-page',settings:'settings-page'};for(const [key,id] of Object.entries(pages)){ $(id).hidden=key!==name;$('nav-'+key).classList.toggle('active',key===name);$('nav-'+key).setAttribute('aria-current',key===name?'page':'false');}const titles={home:['홈','최근 요약과 예약 브리핑을 확인하세요.'],summary:['대화','대화를 읽고, 이 채팅방을 요약하거나 답장을 작성하세요.'],batch:['여러 방 요약','체크한 채팅방만 한 번에 요약합니다. 대화 열기와는 별도로 선택하세요.'],schedule:['매일, 놓치지 않도록.','대화 요약과 일정 확인을 원하는 시간에 예약하세요.'],todos:['해야 할 일, 한곳에.','대화에서 찾은 할 일을 모으고 직접 추가하세요.'],settings:['내 PC에 맞게 연결하세요.','설치부터 AI 연결 확인까지 한곳에서 설정합니다.']};$('page-title').textContent=titles[name][0];$('page-description').textContent=titles[name][1];renderSelected();if(state){renderSchedule();renderTodos();renderHome();renderReports();}updateSummaryControls();if(name==='settings')refreshSetup();if(name==='summary'&&!roomsLoaded&&!roomsLoading&&!tutorialNavigating&&!tutorialActive)loadConversationRooms();if(tutorialActive)tutorialRenderTarget();window.scrollTo(0,0);}
function message(m) { const item = text('div','','message'); item.append(text('span',`${m.sender || '발신자 미상'} · ${m.sentAt ? new Date(m.sentAt).toLocaleString('ko-KR') : '시간 미기재'}`,'source'),text('p',m.text || `[${m.kind || '첨부 메시지'}]`)); return item; }
function renderReports() {
  const reports = activeRoom ? [state.reports?.[activeRoom.id]].filter(Boolean) : [];
  renderBatchReports();
  renderHome();
  $('reportCount').textContent = reports.length;
  $('eventCount').textContent = reports.reduce((n,r)=>n+(r.events || []).length,0);
  $('lastRun').textContent = state.lastRun ? `최근 확인 ${new Date(state.lastRun).toLocaleString('ko-KR')}` : '아직 확인한 대화가 없습니다.';
  $('modeLabel').textContent = reports.some(r=>r.summary) ? 'AI 요약' : '대화 발췌';
  if (!reports.length) { $('reports').replaceChildren(emptyReport.cloneNode(true)); return; }
  $('reports').replaceChildren();
  for (const r of reports) {
    const article = text('article','','report'); article.append(text('h3',r.title));
    article.append(text('p',`${({all:'전체 대화',today:'오늘 대화',incremental:'새 대화',range:'기간 대화'})[r.scope] || '대화'} ${(r.messages || []).length}개 · ${r.checkedAt ? new Date(r.checkedAt).toLocaleString('ko-KR') : ''}`,'report-sub'));
    if (r.error) article.append(text('p',errors[r.error] || `읽기 실패: ${r.error}`,'error'));
    if (r.truncated) article.append(text('p','수집 한도에 도달했습니다. 이 결과에 모든 메시지가 포함되지는 않았습니다.','tag-warn'));
    if (tab === 'events') {
      article.append(text('p','날짜·시간 표현을 포함한 원문입니다. 일정 확정 여부를 확인해 주세요.','report-sub'));
      const events = r.events || []; if (!events.length) article.append(text('p','이번 확인에서 일정 후보를 찾지 못했습니다.','report-sub'));
      events.forEach(m=>article.append(message(m)));
    } else {
      if (r.summary) article.append(text('div',typeof r.summary === 'string' ? r.summary : JSON.stringify(r.summary,null,2),'summary-text'));
      else article.append(text('p','수집한 대화 원문입니다. AI로 요약하면 핵심 내용·할 일·일정을 정리합니다.','report-sub'));
      const details = document.createElement('details'); details.open = !r.summary; details.append(text('summary',`대화 원문 ${(r.messages || []).length}개 보기`)); (r.messages || []).forEach(m=>details.append(message(m))); article.append(details);
      if(r.suggestedTasks?.length){const suggestions=text('div','','task-suggestions');suggestions.append(text('h4','요약에서 찾은 할 일'));r.suggestedTasks.forEach((task,index)=>{const row=text('div','','suggested-task');const info=text('div');info.append(text('strong',task.title),text('span',`담당: ${task.assignee || '미기재'} · 기한: ${task.due || '미기재'}`));const add=text('button','할 일로 추가');add.onclick=()=>busyButton(add,async()=>{state=await api('tasks',{action:'suggestion',roomId:r.id,index});renderTodos();notice('할 일 목록에 추가했습니다.');});row.append(info,add);suggestions.append(row);});article.append(suggestions);}
    }
    $('reports').append(article);
  }
}
async function busy(id, task) { const b=$(id), original=[...b.childNodes]; b.disabled=true;b.textContent='확인 중…'; try {await task();} catch(e){notice(e.message);} finally{b.disabled=false;b.replaceChildren(...original);updateSummaryControls();} }
$('refresh').onclick=()=>busy('refresh',async()=>{notice('카카오톡 채팅방 목록을 읽고 있습니다.'); const result=await api('rooms');rooms=result.rooms || [];roomsLoaded=true;renderRooms();notice(`${rooms.length}개 채팅방을 불러왔습니다.`);});
$('search').oninput=()=>{roomLimit=100;renderRooms();};
$('enabled').onchange=()=>{dirty=true;notice('설정을 저장하면 적용됩니다.');};
async function saveSettings(scope='selection'){
 const tutorialStamp=scope==='schedule'?tutorialBegin('schedule-saved'):null;
 const payload=scope==='schedule'?{enabled:$('enabled').checked,time:$('time').value,scheduleSelected:[...scheduled.values()]}:scope==='provider'?{provider:$('provider').value}:scope==='todos'?{autoTodos:$('auto-todos').checked}:{selected:[...chosen.values()]};
 state=await api('settings',payload);dirty=false;renderReports();renderSchedule();renderTodos();providerStatus();if(scope==='schedule')tutorialAction('schedule-saved',tutorialStamp,{targetCount:payload.scheduleSelected.length,time:payload.time});notice(scope==='selection'?`${chosen.size}개 채팅방 선택을 저장했습니다.`:scope==='schedule'?'예약 설정을 저장했습니다.':scope==='provider'?'AI 선택을 저장했습니다.':'할 일 설정을 저장했습니다.');
}
$('save').onclick=()=>busy('save',()=>saveSettings('schedule'));
$('save-selection').onclick=()=>busy('save-selection',()=>saveSettings('selection'));
async function check(scope){
  const tutorialStamp=tutorialBegin('batch-summary');
  if(!state)throw Error('프로그램 연결을 준비하고 있습니다.');
  if(aiRequestRunning)throw Error('다른 AI 작업이 진행 중입니다.');
  if(!chosen.size)throw Error('요약할 채팅방을 한 개 이상 체크해 주세요.');
  const targets=[...chosen.values()].map(r=>({...r})),start=$('summary-start').value,end=$('summary-end').value;
  if(scope==='range'&&(!start||!end||start>end))throw Error('시작일과 종료일을 확인해 주세요.');
  aiRequestRunning=true;setAIControls(true);
  $('batch-progress').textContent=`${targets.length}개 채팅방 · ${scope==='all'?'전체':scope==='today'?'오늘':start+' ~ '+end} 요약 중`;
  notice('선택한 '+targets.length+'개 채팅방을 요약하고 있습니다. 중간 취소는 지원하지 않습니다.');
  try{state=await api('check',{ai:true,scope,roomIds:targets.map(r=>r.id),start,end});if(targets.every(r=>state.reports?.[r.id]&&!state.reports[r.id].error&&typeof state.reports[r.id].summary==='string'&&state.reports[r.id].summary.trim()))tutorialAction('batch-summary',tutorialStamp,{roomIds:targets.map(r=>r.id)});batchResultIds=targets.map(r=>r.id);batchHasRun=true;batchResultMeta=targets.map(r=>r.title).join(', ')+' · '+(scope==='all'?'전체 대화':scope==='today'?'오늘 대화':start+' ~ '+end);renderReports();renderTodos();$('batch-progress').textContent='요약 작업 완료 · 아래 결과를 확인하세요.';notice('AI 요약을 저장했습니다.');}finally{aiRequestRunning=false;setAIControls(false);}
}
$('summarize-all').onclick=()=>busy('summarize-all',()=>check('all'));
$('summarize-today').onclick=()=>busy('summarize-today',()=>check('today'));
$('setup-schedule').onclick=()=>page('schedule');
$('nav-summary').onclick=()=>page('summary');$('nav-batch').onclick=()=>page('batch');$('nav-schedule').onclick=()=>page('schedule');
$('nav-todos').onclick=()=>page('todos');
function theme(mode){document.documentElement.dataset.theme=mode;localStorage.setItem('brief-theme',mode);$('theme-light').setAttribute('aria-pressed',String(mode==='light'));$('theme-dark').setAttribute('aria-pressed',String(mode==='dark'));}
$('theme-light').onclick=()=>theme('light');$('theme-dark').onclick=()=>theme('dark');theme(localStorage.getItem('brief-theme') || (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));
function providerStatus(){const id=$('provider').value,found=providerList.find(p=>p.id===id),checked=connectionChecks.get(id);$('active-ai-label').textContent='사용 AI: '+(providerList.find(p=>p.id===state?.provider)?.name||state?.provider||id);$('providerStatus').textContent=checked?.ok?'연결 확인 완료':found?.installed?(id==='gemini'?'설치됨 · 개인 계정은 추가 연결 필요':'설치됨 · 로그인은 연결 테스트로 확인'):'설치 필요 · AI 설치·설정에서 시작';}
$('provider').onchange=()=>{dirty=true;providerStatus();notice('AI 선택을 바꿨습니다. 설정을 저장해 주세요.');};
$('time').onchange=()=>{dirty=true;tutorialAction('schedule-time',tutorialBegin('schedule-time'));notice('시간 설정을 저장해 주세요.');};
$('test-provider').onclick=()=>busy('test-provider',()=>testProviderConnection($('provider').value));
for(const name of ['summary','events']) $('tab-'+name).onclick=()=>{tab=name;for(const n of ['summary','events']) $('tab-'+n).setAttribute('aria-selected',String(n===name));renderReports();};
fetch('/api/state').then(r=>r.json()).then(data=>{state=data;token=data.token;providerList=data.providers;chosen=new Map(state.selected.map(r=>[r.id,r]));scheduled=new Map((state.scheduleSelected||[]).map(r=>[r.id,r]));rooms=state.selected;$('enabled').checked=state.enabled;$('time').value=state.time;$('provider').value=state.provider;refreshSelect('provider');$('auto-todos').checked=!!state.autoTodos;providerStatus();renderRooms();renderReports();renderSchedule();renderTodos();renderHome();page('home');if(state.job?.error)notice(state.job.error);if(!state.tutorialSeen||state.tutorialVersion!==state.tutorialCurrentVersion)openTutorial();}).catch(()=>notice('로컬 서버에 연결하지 못했습니다. 페이지를 다시 열어 주세요.'));
const tutorialSteps=[
  {title:'AI 연결 확인',page:'settings',description:'카카오와 무관한 비공식 프로그램입니다. 이용·면책 고지는 설정에서 확인할 수 있습니다. Node.js는 따로 설치하지 않아도 됩니다. AI 설치·설정에서 도구를 설치한 뒤 로그인 명령을 복사해 PowerShell에서 실행하고, 연결 테스트를 눌러 확인하세요. 요약·답장 생성은 선택한 방의 대화를 AI 서비스에 보내며 이용 한도에 포함됩니다.',checks:[['ai-connected','연결 테스트 성공']]},
  {title:'채팅방 검색하고 열기',page:'summary',description:'채팅방 새로고침을 누르고 검색창에 방 이름을 입력한 뒤 결과를 눌러 대화를 엽니다. 목록 새로고침과 대화 열기는 사용자가 직접 눌렀을 때 실행됩니다.',checks:[['room-search','방 이름 검색'],['room-open','대화 열기 성공']]},
  {title:'이 방 요약하기',page:'summary',description:'오늘·전체·기간 중 범위를 선택하고 이 방을 요약해 봅니다. 기간을 고르면 시작일과 종료일도 입력하세요.',checks:[['single-scope','요약 범위 선택'],['single-summary','오류 없는 요약 결과']]},
  {title:'여러 방 요약하기',page:'batch',description:'목록을 새로고침하고 한 개 이상 체크한 뒤 요약을 실행합니다. 각 방에 요약 오류가 있으면 완료로 표시하지 않습니다.',checks:[['batch-selected','채팅방 체크'],['batch-summary','오류 없는 요약 결과']]},
  {title:'내 말투 답장 초안',page:'summary',description:'이 방의 내 말투로 AI 초안을 만들고 직접 고쳐 저장합니다. 초안 생성은 선택한 방의 대화를 AI 서비스에 보내고 이용 한도에 포함됩니다. 실제 발송은 하지 않습니다.',checks:[['reply-generated','초안 생성 성공'],['draft-edited','초안을 직접 수정'],['draft-saved','수정한 초안 저장 성공']]},
  {title:'전송 방법 익히기',page:'summary',description:'답장 입력란에서 Enter는 전송, Shift+Enter는 줄 바꿈입니다. AI 초안을 만들었다면 내용을 직접 확인·수정한 뒤 전송할 수 있습니다. 이 단계에서는 전송하지 않습니다.',checks:[['send-method','전송 방법 확인']]},
  {title:'할 일 추가하기',page:'todos',description:'할 일 내용을 직접 입력하고 추가해 봅니다. 안내가 예시 문장을 입력란에 대신 넣지는 않습니다.',checks:[['todo-added','할 일 추가 성공']]},
  {title:'예약 대상과 시간 저장',page:'schedule',description:'예약 대상 방과 시간을 확인하고 저장합니다. 기존 설정이 맞다면 그대로 저장해도 됩니다. 일일 확인은 원할 때만 직접 켜세요.',checks:[['schedule-target','예약 대상 확인'],['schedule-time','시간 확인'],['schedule-saved','대상·시간 저장 성공']]}
];
let tutorialStep=0,tutorialRun=0,tutorialStamp=0,tutorialActive=false,tutorialNavigating=false,tutorialHighlight=null,tutorialGeneratedDraft=null;
const tutorialEvents=new Map(),tutorialSkipped=new Set(),tutorialBatchSelections=new Set(),tutorialScheduleSelections=new Set();
function tutorialStepEvents(){if(!tutorialEvents.has(tutorialStep))tutorialEvents.set(tutorialStep,new Set());return tutorialEvents.get(tutorialStep);}
function tutorialBegin(action){return tutorialActive&&tutorialSteps[tutorialStep].checks.some(([name])=>name===action)?tutorialStamp:null;}
function tutorialHas(action,stamp=tutorialStamp){return !!stamp&&stamp===tutorialStamp&&tutorialStepEvents().has(action);}
function tutorialAction(action,stamp,context={}){
  if(!stamp||stamp!==tutorialStamp||!tutorialActive||!tutorialSteps[tutorialStep].checks.some(([name])=>name===action))return false;
  if(action==='batch-selected'&&context.roomId)tutorialBatchSelections.add(String(context.roomId));
  if(action==='batch-summary'&&!context.roomIds?.some(id=>tutorialBatchSelections.has(String(id))))return false;
  if(action==='schedule-target'&&context.roomId)tutorialScheduleSelections.add(String(context.roomId));
  if(action==='draft-saved'&&!tutorialHas('draft-edited',stamp))return false;
  if(action==='schedule-saved'&&(context.targetCount<1||!/^([01]\d|2[0-3]):[0-5]\d$/.test(context.time||'')))return false;
  if(action==='schedule-saved'){tutorialStepEvents().add('schedule-target');tutorialStepEvents().add('schedule-time');}
  tutorialStepEvents().add(action);renderTutorial();return true;
}
function tutorialTargetSelector(){switch(tutorialStep){case 0:return '#test-provider';case 1:return !roomsLoaded?'#chat-refresh-list':tutorialHas('room-search')?(document.querySelector('#chat-rooms .conversation-room')?'#chat-rooms .conversation-room':'#chat-rooms'):'#chat-search';case 2:return !activeRoom?'#chat-refresh-list':tutorialHas('single-scope')?'#summarize-this-room':'#room-scope';case 3:return !roomsLoaded?'#refresh':tutorialHas('batch-selected')?'#summarize-today':'#rooms';case 4:return !activeRoom?'#chat-refresh-list':!tutorialHas('reply-generated')?'#chat-generate':!tutorialHas('draft-edited')?'#chat-draft':'#chat-save';case 5:return '#chat-draft';case 6:return '#todo-title';default:return !roomsLoaded?'#schedule-refresh':tutorialHas('schedule-target')?'#save':'#schedule-room-list';}}
function tutorialRenderTarget(){
  tutorialHighlight?.classList.remove('tutorial-highlight');tutorialHighlight=null;
  if(!tutorialActive||currentPage!==tutorialSteps[tutorialStep].page){$('tutorial-guide').classList.remove('guide-left');$('tutorial-guide').classList.add('guide-right');return;}
  const target=document.querySelector(tutorialTargetSelector());if(!target||!target.getClientRects().length)return;
  tutorialHighlight=target;target.classList.add('tutorial-highlight');const rect=target.getBoundingClientRect(),guide=$('tutorial-guide');
  guide.classList.toggle('guide-left',rect.left+rect.width/2>innerWidth/2);guide.classList.toggle('guide-right',rect.left+rect.width/2<=innerWidth/2);
  guide.classList.toggle('guide-top',rect.top+rect.height/2>innerHeight/2);guide.classList.toggle('guide-bottom',rect.top+rect.height/2<=innerHeight/2);
  target.scrollIntoView({behavior:'smooth',block:'center',inline:'nearest'});
}
function renderTutorial(){
  const step=tutorialSteps[tutorialStep],events=tutorialStepEvents(),complete=tutorialSkipped.has(tutorialStep)||step.checks.every(([name])=>events.has(name));
  $('tutorial-step-label').textContent=`${tutorialStep+1} / ${tutorialSteps.length}`;$('tutorial-progress').value=tutorialStep+1;
  $('tutorial-title').textContent=step.title;$('tutorial-description').textContent=step.description;
  const list=$('tutorial-checklist');list.replaceChildren();for(const [name,label]of step.checks){const item=text('li',(events.has(name)?'✓ ':'○ ')+label);item.classList.toggle('done',events.has(name));list.append(item);}
  $('tutorial-prev').disabled=tutorialStep===0;$('tutorial-next').hidden=tutorialStep===tutorialSteps.length-1;$('tutorial-next').disabled=!complete;
  $('tutorial-finish').hidden=tutorialStep!==tutorialSteps.length-1;$('tutorial-finish').disabled=!complete;
  $('tutorial-confirm-step').hidden=tutorialStep!==5;$('tutorial-confirm-step').disabled=complete;
  $('tutorial-skip').disabled=tutorialSkipped.has(tutorialStep);
  $('tutorial-status').textContent=tutorialSkipped.has(tutorialStep)?'이 단계를 건너뛰었습니다. 다음을 눌러 계속할 수 있습니다.':complete?'단계를 마쳤습니다. 다음을 눌러 계속하세요.':`이번 단계에서 ${step.checks.filter(([name])=>!events.has(name)).map(([,label])=>label).join(', ')}을(를) 진행해 보세요.`;
  $('tutorial-guide').hidden=!tutorialActive;tutorialRenderTarget();
}
function tutorialEnterStep(index){tutorialHighlight?.classList.remove('tutorial-highlight');tutorialHighlight=null;tutorialStep=index;tutorialStamp++;tutorialNavigating=true;page(tutorialSteps[index].page);tutorialNavigating=false;renderTutorial();}
function openTutorial(){if(tutorialActive)return;tutorialActive=true;tutorialRun++;tutorialStep=0;tutorialStamp++;tutorialEvents.clear();tutorialSkipped.clear();tutorialBatchSelections.clear();tutorialScheduleSelections.clear();tutorialGeneratedDraft=null;tutorialEnterStep(0);$('tutorial-go').focus();}
async function closeTutorial(action){const controls=['tutorial-close','tutorial-later','tutorial-go','tutorial-prev','tutorial-next','tutorial-skip','tutorial-finish'];controls.forEach(id=>$(id).disabled=true);$('tutorial-status').textContent='기록 중…';const run=tutorialRun;try{const result=await api('tutorial',{action});if(run!==tutorialRun)return;state.tutorialVersion=result.tutorialVersion;state.tutorialSeen=true;tutorialActive=false;tutorialStamp++;tutorialHighlight?.classList.remove('tutorial-highlight');tutorialHighlight=null;$('tutorial-guide').hidden=true;}catch(error){$('tutorial-status').textContent='저장하지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요. '+error.message;}finally{controls.forEach(id=>$(id).disabled=false);}}
$('tutorial-prev').onclick=()=>{if(tutorialStep>0)tutorialEnterStep(tutorialStep-1);};$('tutorial-next').onclick=()=>{if(tutorialStep<tutorialSteps.length-1&&!$('tutorial-next').disabled)tutorialEnterStep(tutorialStep+1);};$('tutorial-skip').onclick=()=>{tutorialSkipped.add(tutorialStep);renderTutorial();};$('tutorial-finish').onclick=()=>{if(!$('tutorial-finish').disabled)closeTutorial('finish');};$('tutorial-later').onclick=$('tutorial-close').onclick=()=>closeTutorial('dismiss');$('tutorial-go').onclick=()=>{tutorialNavigating=true;page(tutorialSteps[tutorialStep].page);tutorialNavigating=false;tutorialRenderTarget();};$('tutorial-confirm-step').onclick=()=>tutorialAction('send-method',tutorialBegin('send-method'));$('tutorial-replay').onclick=openTutorial;
setInterval(async()=>{if(dirty)return;try{const data=await fetch('/api/state').then(r=>r.json());if(data.lastRun!==state.lastRun||data.job?.finishedAt!==state.job?.finishedAt){state=data;renderReports();if(data.job?.error)notice(data.job.error);}}catch{}},10000);

async function busyButton(button,task){const label=button.textContent;button.disabled=true;try{await task();}catch(e){notice(e.message);}finally{button.disabled=false;button.textContent=label;}}
function showSummary(open){$('summary-side').hidden=!open;$('summary-resizer').hidden=!open;$('chat-workspace').classList.toggle('summary-open',open);$('show-summary').setAttribute('aria-pressed',String(open));$('show-summary').textContent=open?'요약 패널 닫기':'요약 패널 열기';if(open)summaryWidth(Number(localStorage.getItem('brief-summary-width'))||340);}
function rightView(chat){$('chat-view').hidden=false;$('report-view').hidden=false;if(!chat)showSummary(true);}
$('show-summary').onclick=()=>showSummary($('summary-side').hidden);$('show-chat').onclick=()=>showSummary(false);
async function openRoom(room,before=null){
  const tutorialStamp=before?null:tutorialBegin('room-open');
  if(!room)return;if(activeRoom?.id!==room.id){if(activeRoom)sessionDrafts.set(activeRoom.id,$('chat-draft').value);$('reply-style-status').hidden=true;invalidateSendPreview();}const requestId=++historyRequestId;if(!before){const cached=historyCache.get(String(room.id));historyMessages=cached?[...cached.messages]:[];historyAttachments=cached?[...cached.attachments]:[];historyBefore=cached?.before||null;if(cached)renderChat(true);else $('chat-messages').replaceChildren(text('p','대화 내용을 불러오고 있습니다.','chat-empty'));$('chat-draft').value=sessionDrafts.has(room.id)?sessionDrafts.get(room.id):state.drafts?.[room.id]||'';}activeRoom=room;renderConversationRooms();$('room-summary-target').textContent=room.title;updateSummaryControls();renderSendOutcome();updateSendControls();renderReports();rightView(true);$('chat-title').textContent=room.title;$('chat-meta').textContent=historyMessages.length?`이 PC에 저장된 대화 · ${historyMessages.length}개`:'대화 내용을 불러오고 있습니다.';
  if(quietHistoryBusy){queuedHistoryRead={room:{...room},before};return;}quietHistoryBusy=true;
  try{const result=await api('history',{roomId:room.id,beforeId:before});if(String(activeRoom?.id)!==String(room.id)||requestId!==historyRequestId)return;if(before){historyMessages=[...result.messages,...historyMessages];historyAttachments=[...(result.attachments||[]),...historyAttachments];}else{historyMessages=result.messages||[];historyAttachments=result.attachments||[];}historyBefore=result.next_before_id;$('chat-meta').textContent=`이 PC에 저장된 대화 · ${result.coverage?.storedLocally ?? historyMessages.length}개`;historyCache.set(String(room.id),{messages:[...historyMessages],attachments:[...historyAttachments],before:historyBefore});renderChat(!before);if(!before)tutorialAction('room-open',tutorialStamp);}catch(e){if(String(activeRoom?.id)!==String(room.id)||requestId!==historyRequestId)return;$('chat-meta').textContent=e.message;if(!historyMessages.length)$('chat-messages').replaceChildren(text('p',e.message,'chat-empty'));notice(e.message);}finally{quietHistoryBusy=false;const queued=queuedHistoryRead;queuedHistoryRead=null;if(queued&&String(activeRoom?.id)===String(queued.room.id))openRoom(queued.room,queued.before);}
}
function renderChat(scroll=true){
  const container=$('chat-messages');container.replaceChildren();
  if(historyBefore){const more=text('button','이전 대화 불러오기','load-earlier');more.onclick=()=>busyButton(more,()=>openRoom(activeRoom,historyBefore));container.append(more);}
  let day='';for(const m of historyMessages){const date=m.sentAt?new Date(m.sentAt):null;const nextDay=date?date.toLocaleDateString('ko-KR',{year:'numeric',month:'long',day:'numeric',timeZone:'Asia/Seoul'}):'날짜 미기재';if(day!==nextDay){container.append(text('div',nextDay,'chat-day'));day=nextDay;}
    const row=text('div','','chat-row'+(m.fromMe?' mine':''));if(!m.fromMe)row.append(text('div',(m.sender||'?').slice(0,1),'chat-avatar'));const column=text('div','','chat-column');if(!m.fromMe)column.append(text('span',m.sender||'발신자 미상','chat-sender'));const line=text('div','','bubble-line');const bubble=text('div','','bubble');if(m.text)bubble.append(text('p',m.text));
    const attached=historyAttachments.filter(a=>a.messageId===m.id);for(const a of attached){const box=text('div','','chat-attachment');if(a.kind==='photo'){const image=document.createElement('img');image.alt=a.name||'대화에 첨부된 사진';image.loading='lazy';const load=text('button','사진 보기');load.onclick=()=>{image.src=a.url;image.hidden=false;load.hidden=true;};image.hidden=true;image.onerror=()=>{image.hidden=true;box.append(text('p','사진을 열 수 없습니다. 전송된 사진 정보만 표시합니다.','attachment-note'));};if(!a.url){load.disabled=true;load.textContent='사진 정보만 확인 가능';}box.append(image,load);}const title=a.name||(a.kind==='photo'?'사진':a.kind==='video'?'동영상':'첨부파일');box.append(text('strong',title));const meta=[a.kind==='photo'?'이미지':a.kind==='video'?'동영상':'파일',a.size?`${Math.round(a.size/1024)} KB`:'',a.expiresAt?'다운로드 기한 '+new Date(a.expiresAt).toLocaleDateString('ko-KR'):''].filter(Boolean).join(' · ');box.append(text('span',meta,'attachment-note'));if(a.kind!=='photo'){const download=text('button','파일 다운로드');download.onclick=()=>busyButton(download,async()=>{try{const response=await fetch(a.url);if(!response.ok){box.append(text('p','파일을 열 수 없습니다. 전송된 파일 정보만 표시합니다.','attachment-note'));download.hidden=true;return;}const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=a.name||'첨부파일';link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);}catch{box.append(text('p','파일을 열 수 없습니다. 전송된 파일 정보만 표시합니다.','attachment-note'));}});if(!a.url){download.disabled=true;box.append(text('span','파일을 열 수 없어 정보만 표시합니다.','attachment-note'));}if(a.expiresAt&&new Date(a.expiresAt)<new Date()){download.disabled=true;box.append(text('span','다운로드 기한이 지나 파일 정보만 표시합니다.','attachment-note'));}box.append(download);}bubble.append(box);}
    if(!m.text&&!attached.length)bubble.append(text('p',`[${m.kind==='photo'?'사진':m.kind==='file'?'파일':m.kind==='video'?'동영상':m.kind || '메시지'}] 첨부 정보가 없거나 열 수 없습니다.`));line.append(bubble,text('time',date?date.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Seoul'}):'','chat-time'));column.append(line);row.append(column);container.append(row);
  }if(!historyMessages.length)container.append(text('p','이 PC에 저장된 대화가 없습니다.','chat-empty'));if(scroll)container.scrollTop=container.scrollHeight;
}
$('chat-refresh').onclick=()=>busy('chat-refresh',()=>openRoom(activeRoom));
function renderTodos(){if(!state)return;const tasks=(state.todos||[]).filter(t=>!t.archived);$('todoCount').textContent=tasks.filter(t=>!t.done).length;$('todos-list').replaceChildren();for(const task of tasks){const row=text('article','','todo-item'+(task.done?' done':''));const box=document.createElement('input');box.type='checkbox';box.checked=task.done;box.setAttribute('aria-label',task.title+' 완료');box.onchange=async()=>{try{state=await api('tasks',{action:'done',id:task.id,value:box.checked});renderTodos();}catch(e){notice(e.message);}};const info=text('div','','todo-info');info.append(text('strong',task.title),text('span',`${task.due?'기한 '+task.due:'기한 미기재'}${task.assignee?' · '+task.assignee:''}${task.roomTitle?' · '+task.roomTitle:' · 직접 추가'}`));if(task.source){const details=document.createElement('details');details.append(text('summary','근거 대화 보기'),message(task.source));info.append(details);}const archive=text('button','보관');archive.onclick=()=>busyButton(archive,async()=>{state=await api('tasks',{action:'archive',id:task.id,value:true});renderTodos();});row.append(box,info,archive);$('todos-list').append(row);}if(!tasks.length)$('todos-list').append(text('div','등록한 할 일이 없습니다. 직접 추가하거나 요약 결과에서 할 일로 추가해 주세요.','todo-empty'));}
$('todo-form').onsubmit=async e=>{e.preventDefault();const tutorialStamp=tutorialBegin('todo-added');try{state=await api('tasks',{action:'add',title:$('todo-title').value,due:$('todo-due').value});tutorialAction('todo-added',tutorialStamp);$('todo-title').value='';$('todo-due').value='';renderTodos();notice('할 일을 추가했습니다.');}catch(error){notice(error.message);}};
$('auto-todos').onchange=()=>{dirty=true;notice('자동 추가 설정을 저장해 주세요.');};$('save-auto').onclick=()=>busy('save-auto',()=>saveSettings('todos'));
async function generateReply(roomId){const tutorialStamp=tutorialBegin('reply-generated');if(!roomId)throw Error('답장을 작성할 채팅방을 선택해 주세요.');notice('최근 대화를 바탕으로 답장 초안을 작성하고 있습니다.');const result=await api('reply',{roomId,tone:$('reply-tone').value,context:$('reply-context').value});state.drafts=state.drafts||{};state.drafts[roomId]=result.text;if(activeRoom?.id===roomId){if(tutorialAction('reply-generated',tutorialStamp))tutorialGeneratedDraft={roomId,text:result.text,stamp:tutorialStamp};const style=$('reply-style-status');style.hidden=false;style.textContent=result.styleUsed===true?`이 방의 내 메시지 ${Number(result.styleSampleCount)||0}개 말투를 참고했습니다.`:`이 방의 내 메시지 ${Number(result.styleSampleCount)||0}개를 확인했습니다. 말투 참고에 필요한 메시지 샘플이 부족합니다.`;}notice('답장 초안을 만들었습니다. 내용을 확인하고 수정해 주세요.');return result.text;}
$('chat-generate').onclick=()=>busy('chat-generate',async()=>{if(!activeRoom)throw Error('채팅방을 선택해 주세요.');if(aiRequestRunning)throw Error('다른 AI 작업이 진행 중입니다.');const roomId=activeRoom.id,originalDraft=$('chat-draft').value;aiRequestRunning=true;setAIControls(true);try{const draft=await generateReply(roomId);if(activeRoom?.id!==roomId&&!sessionDrafts.has(roomId))sessionDrafts.set(roomId,draft);else if(activeRoom?.id!==roomId&&sessionDrafts.get(roomId)===originalDraft)sessionDrafts.set(roomId,draft);if(activeRoom?.id===roomId&&$('chat-draft').value===originalDraft){invalidateSendPreview();$('chat-draft').value=draft;sessionDrafts.set(roomId,draft);updateSendControls();}}finally{aiRequestRunning=false;setAIControls(false);}});
$('chat-copy').onclick=()=>busy('chat-copy',async()=>{await navigator.clipboard.writeText($('chat-draft').value);notice('답장 초안을 복사했습니다.');});
$('chat-save').onclick=()=>busy('chat-save',async()=>{if(!activeRoom)throw Error('먼저 대화를 열어 주세요.');const roomId=activeRoom.id,title=activeRoom.title,body=$('chat-draft').value,generated=tutorialGeneratedDraft,tutorialStamp=generated?.roomId===roomId&&generated.text!==body?generated.stamp:null;await api('save-draft',{roomId,text:body});state.drafts=state.drafts||{};state.drafts[roomId]=body;if(tutorialHas('draft-edited',tutorialStamp))tutorialAction('draft-saved',tutorialStamp);notice(title+' 초안을 저장했습니다.');});
function renderScheduled(){
  const list=$('schedule-room-list'),query=$('schedule-search').value.trim().toLocaleLowerCase();list.replaceChildren();
  const matches=rooms.filter(r=>r.title.toLocaleLowerCase().includes(query));
  for(const room of matches.slice(0,scheduleLimit)){const label=text('label','','schedule-room-option');const input=document.createElement('input');input.type='checkbox';input.checked=scheduled.has(room.id);input.setAttribute('aria-label',room.title+' 예약 대상');input.onchange=()=>{if(input.checked){scheduled.set(room.id,{id:room.id,title:room.title});tutorialAction('schedule-target',tutorialBegin('schedule-target'),{roomId:room.id});}else scheduled.delete(room.id);dirty=true;renderScheduled();notice('예약 대상 변경을 저장해 주세요.');};label.append(input,text('span',room.title));list.append(label);}
  if(matches.length>scheduleLimit){const more=text('button',`다음 ${Math.min(100,matches.length-scheduleLimit)}개 보기`,'list-more');more.onclick=()=>{scheduleLimit+=100;renderScheduled();};list.append(more);}
  if(rooms.length&&!matches.length)list.append(text('p','검색 결과가 없습니다.','empty-small'));
  if(!rooms.length)list.append(text('p','채팅방 새로고침을 눌러 목록을 불러와 주세요.','empty-small'));
  $('reservation-rooms').replaceChildren();for(const room of [...scheduled.values()].slice(0,50)){const chip=text('div','','selected-chip');chip.append(text('span',room.title));const remove=text('button','×');remove.setAttribute('aria-label',room.title+' 예약 해제');remove.onclick=()=>{scheduled.delete(room.id);dirty=true;renderScheduled();};chip.append(remove);$('reservation-rooms').append(chip);}if(scheduled.size>50)$('reservation-rooms').append(text('p',`외 ${scheduled.size-50}개 채팅방`,'selection-overflow'));if(!scheduled.size)$('reservation-rooms').append(text('p','예약 대상 채팅방을 선택해 주세요.','reservation-empty'));
}
$('schedule-search').oninput=()=>{scheduleLimit=100;renderScheduled();};
$('schedule-refresh').onclick=()=>busy('schedule-refresh',async()=>{notice('예약용 채팅방 목록을 불러오고 있습니다.');const result=await api('rooms');rooms=result.rooms||[];roomsLoaded=true;renderScheduled();renderRooms();notice('채팅방 목록을 불러왔습니다. 예약 대상은 별도로 선택해 주세요.');});
async function summarizeRoom(scope){
  const tutorialStamp=tutorialBegin('single-summary');
  if(!activeRoom)throw Error('먼저 대화를 열어 주세요.');
  if(aiRequestRunning)throw Error('다른 AI 작업이 진행 중입니다.');
  const target={...activeRoom},start=$('room-start').value,end=$('room-end').value;
  if(scope==='range'&&(!start||!end||start>end))throw Error('시작일과 종료일을 확인해 주세요.');
  aiRequestRunning=true;setAIControls(true);notice(target.title+' · '+(scope==='all'?'전체':scope==='today'?'오늘':start+' ~ '+end)+' 요약 중');
  try{state=await api('check',{ai:true,scope,roomId:target.id,start,end});const report=state.reports?.[target.id];if(report&&!report.error&&typeof report.summary==='string'&&report.summary.trim())tutorialAction('single-summary',tutorialStamp);renderReports();renderTodos();if(activeRoom?.id===target.id)showSummary(true);notice(target.title+' 요약을 저장했습니다.');}finally{aiRequestRunning=false;setAIControls(false);}
}
$('summarize-this-room').onclick=()=>busy('summarize-this-room',()=>summarizeRoom($('room-scope').value));
$('summarize-this-today').onclick=()=>busy('summarize-this-today',()=>summarizeRoom('today'));
$('room-scope').onchange=()=>{$('room-date-range').hidden=$('room-scope').value!=='range';tutorialAction('single-scope',tutorialBegin('single-scope'));};
const customSelects=new Map();
function refreshSelect(id){const control=customSelects.get(id);if(!control)return;const native=$(id),option=native.options[native.selectedIndex];control.trigger.textContent=option?.textContent||'선택';control.trigger.setAttribute('aria-label',(id==='provider'?'요약에 사용할 AI':id==='room-scope'?'요약 범위':'답장 말투')+' '+(option?.textContent||''));for(const button of control.menu.children){const selected=button.dataset.value===native.value;button.setAttribute('aria-selected',String(selected));}}
function enhanceSelect(id){const native=$(id),wrap=text('div','','custom-select'),trigger=text('button','','select-trigger'),menu=text('div','','select-menu');trigger.type='button';trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');menu.setAttribute('role','listbox');menu.setAttribute('aria-label',id==='provider'?'AI 선택':id==='room-scope'?'요약 범위 선택':'말투 선택');menu.hidden=true;native.before(wrap);wrap.append(native,trigger,menu);native.hidden=true;
  const close=()=>{menu.hidden=true;trigger.setAttribute('aria-expanded','false');};
  for(const option of native.options){const button=text('button',option.textContent,'select-option');button.type='button';button.setAttribute('role','option');button.dataset.value=option.value;button.onclick=()=>{native.value=option.value;native.dispatchEvent(new Event('change'));refreshSelect(id);close();trigger.focus();};button.onkeydown=e=>{const items=[...menu.children],index=items.indexOf(button);if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();items[(index+(e.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();}if(e.key==='Escape'){close();trigger.focus();}if(e.key==='Tab')close();};menu.append(button);}
  trigger.onclick=()=>{const opening=menu.hidden;menu.hidden=!opening;trigger.setAttribute('aria-expanded',String(opening));if(opening)menu.children[native.selectedIndex]?.focus();};trigger.onkeydown=e=>{if(e.key==='ArrowDown'){e.preventDefault();menu.hidden=false;trigger.setAttribute('aria-expanded','true');menu.children[native.selectedIndex]?.focus();}if(e.key==='Escape')close();};document.addEventListener('click',e=>{if(!wrap.contains(e.target))close();});customSelects.set(id,{trigger,menu});native.addEventListener('change',()=>refreshSelect(id));refreshSelect(id);
}
enhanceSelect('provider');enhanceSelect('reply-tone');enhanceSelect('room-scope');
function renderHome(){
  if(!state)return;const history=state.history?.length?state.history:Object.entries(state.reports||{}).filter(([,r])=>r.summary).map(([id,r])=>({id:'latest-'+id,roomId:id,...r,messageCount:r.messages?.length||0}));const ordered=[...history].sort((a,b)=>(b.checkedAt||'').localeCompare(a.checkedAt||''));const latest=new Map();for(const item of ordered)if(!latest.has(item.roomId))latest.set(item.roomId,item);
  const unfinished=(state.todos||[]).filter(t=>!t.done&&!t.archived).length;$('home-stats').replaceChildren();for(const [label,value]of[['요약한 채팅방',latest.size],['쌓인 브리핑',history.length],['예약한 채팅방',(state.scheduleSelected||[]).length],['남은 할 일',unfinished]]){const stat=text('div','','home-stat');stat.append(text('span',label),text('strong',value));$('home-stats').append(stat);}
  $('home-last-run').textContent=state.lastRun?'최근 확인 '+new Date(state.lastRun).toLocaleString('ko-KR'):'채팅방을 선택해 첫 브리핑을 만들어 보세요.';$('overall-brief').replaceChildren();for(const item of latest.values()){const row=text('button','','overall-row');row.append(text('strong',item.title),text('span',item.summary.split('\n').filter(Boolean).slice(0,2).join(' ').slice(0,240)));row.onclick=()=>openBriefing(item,true);$('overall-brief').append(row);}if(!latest.size)$('overall-brief').append(text('p','요약을 실행하면 채팅방별 핵심 내용이 여기에 모입니다.','home-empty'));
  $('home-feed').replaceChildren();const filtered=ordered.filter(r=>!$('scheduled-only').checked||r.scheduled);for(const item of filtered.slice(0,feedLimit)){const card=text('article','','feed-card');const top=text('div','','feed-card-top');top.append(text('span',item.scheduled?'예약 브리핑':item.scheduled===null?'이전 브리핑':'대화 브리핑','feed-type'),text('time',item.checkedAt?new Date(item.checkedAt).toLocaleString('ko-KR'):'','source'));card.append(top,text('h3',item.title));const scopeLabel=({all:'전체 대화',today:'오늘 대화',range:'기간 대화',incremental:'새 대화'})[item.scope]||'대화';card.append(text('p',`${scopeLabel} ${item.messageCount??0}개${item.dateRange?' · '+item.dateRange.start+' ~ '+item.dateRange.end:''}`,'report-sub'));const detail=document.createElement('details');detail.append(text('summary','요약 전체 보기'),text('div',item.summary,'summary-text'));card.append(text('p',item.summary.slice(0,210)+(item.summary.length>210?'…':''),'feed-preview'),detail);if(item.truncated)card.append(text('p','수집 한도에 도달한 결과입니다.','tag-warn'));const actions=text('div','','feed-actions');const view=text('button','대화 보기');view.onclick=()=>openBriefing(item,false);const summary=text('button','요약 보기');summary.onclick=()=>openBriefing(item,true);actions.append(view,summary);card.append(actions);$('home-feed').append(card);}if(filtered.length>feedLimit){const more=text('button',`이전 브리핑 ${Math.min(20,filtered.length-feedLimit)}개 더 보기`,'feed-more');more.onclick=()=>{feedLimit+=20;renderHome();};$('home-feed').append(more);}if(!filtered.length)$('home-feed').append(text('div',$('scheduled-only').checked?'아직 예약으로 생성된 브리핑이 없습니다. 예약을 설정하면 이곳에 누적됩니다.':'아직 브리핑이 없습니다. 대화 요약 화면에서 시작해 주세요.','home-empty'));
}
async function openBriefing(item,summary){page('summary');await openRoom({id:item.roomId,title:item.title});if(summary&&activeRoom?.id===item.roomId){$('reports').replaceChildren();const article=text('article','','report');article.append(text('h3',item.title),text('p',item.checkedAt?new Date(item.checkedAt).toLocaleString('ko-KR'):'','report-sub'),text('div',item.summary,'summary-text'));$('reports').append(article);showSummary(true);}}
$('nav-home').onclick=()=>page('home');$('home-open-chat').onclick=()=>page('summary');$('home-open-schedule').onclick=()=>page('schedule');$('scheduled-only').onchange=()=>{feedLimit=20;renderHome();};
$('summarize-range').onclick=()=>busy('summarize-range',()=>check('range'));
for(const [button,clear,isSchedule]of[['select-all','clear-all',false],['schedule-select-all','schedule-clear-all',true]]){
  $(button).onclick=()=>{const query=$(isSchedule?'schedule-search':'search').value.trim().toLocaleLowerCase(),target=isSchedule?scheduled:chosen,action=isSchedule?'schedule-target':'batch-selected',stamp=tutorialBegin(action);for(const r of rooms.filter(r=>r.title.toLocaleLowerCase().includes(query))){target.set(r.id,{id:r.id,title:r.title});if(stamp)tutorialAction(action,stamp,{roomId:r.id});}dirty=true;renderRooms();notice(isSchedule?'예약 대상을 선택했습니다. 예약 설정을 저장해 주세요.':'검색 결과를 요약 대상으로 선택했습니다.');};
  $(clear).onclick=()=>{(isSchedule?scheduled:chosen).clear();dirty=true;renderRooms();notice(isSchedule?'예약 선택을 해제했습니다. 예약 설정을 저장해 주세요.':'여러 방 요약의 선택을 모두 해제했습니다.');};
}
const todayKST=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());$('summary-start').value=todayKST;$('summary-end').value=todayKST;$('room-start').value=todayKST;$('room-end').value=todayKST;
function summaryWidth(value){const max=Math.max(250,Math.min(680,$('chat-workspace').clientWidth-500));const width=Math.max(250,Math.min(max,value));$('chat-workspace').style.setProperty('--summary-width',width+'px');$('summary-resizer').setAttribute('aria-valuenow',String(Math.round(width)));localStorage.setItem('brief-summary-width',String(width));}
$('chat-workspace').style.setProperty('--summary-width',(Number(localStorage.getItem('brief-summary-width'))||340)+'px');
$('summary-resizer').onpointerdown=e=>{e.preventDefault();const handle=e.currentTarget;handle.setPointerCapture(e.pointerId);handle.onpointermove=event=>summaryWidth($('chat-workspace').getBoundingClientRect().right-event.clientX);const end=()=>{handle.onpointermove=null;handle.onpointerup=null;handle.onpointercancel=null;};handle.onpointerup=end;handle.onpointercancel=end;};
$('summary-resizer').onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();summaryWidth(Number(e.currentTarget.getAttribute('aria-valuenow'))+(e.key==='ArrowLeft'?20:-20));}};
function setAIControls(disabled){
  for(const id of ['summarize-all','summarize-today','summarize-range','summarize-this-room','summarize-this-today','chat-generate','test-provider'])$(id).disabled=disabled;
  document.body.classList.toggle('ai-working',disabled);
  $('notice').setAttribute('aria-busy',String(disabled));
  updateSendControls();updateSummaryControls();renderRooms();
}
async function testProviderConnection(provider){
  const tutorialStamp=tutorialBegin('ai-connected');
  if(!token||!state)throw Error('프로그램 연결을 준비하고 있습니다. 잠시 후 다시 시도해 주세요.');
  if(aiRequestRunning)throw Error('다른 AI 작업이 진행 중입니다. 완료 후 다시 시도해 주세요.');
  aiRequestRunning=true;setAIControls(true);
  notice('가상 메시지로 AI 연결을 테스트하고 있습니다. 실제 대화는 보내지 않습니다.');
  try{
    await api('test-provider',{provider});
    connectionChecks.set(provider,{ok:true,checkedAt:new Date().toISOString()});
    tutorialAction('ai-connected',tutorialStamp);
    notice('AI 연결을 확인했습니다.');
  }catch(error){connectionChecks.set(provider,{ok:false,message:error.message});throw error;}
  finally{aiRequestRunning=false;setAIControls(false);providerStatus();if(setupState)renderSetup();}
}
const installJobs=new Map();
const loginCommands={codex:'codex login',claude:'claude auth login',gemini:'gemini'};
async function getSetup(path='setup'){
  const response=await fetch('/api/'+path,{cache:'no-store'});let result;
  try{result=await response.json();}catch{throw Error('설치 상태를 읽지 못했습니다. 프로그램을 다시 실행해 주세요.');}
  if(!response.ok||result.error)throw Error(result.error||'설치 상태를 읽지 못했습니다.');
  return result;
}
function setupMessage(message,error=false){$('setup-notice').textContent=message;$('setup-notice').classList.toggle('error',error);}
async function refreshSetup(){
  $('refresh-setup').disabled=true;
  try{
    setupState=await getSetup();
    if(Array.isArray(setupState.providers))providerList=setupState.providers;
    $('program-version').textContent=setupState.version||'테스트 버전';
    $('program-mode').textContent=setupState.desktop?'Windows 데스크톱 앱':'이 PC의 로컬 웹 화면';
    $('app-build-label').textContent=(setupState.version?'v'+setupState.version+' · ':'')+'테스트 버전';
    setupMessage('설치됨은 로그인 완료를 뜻하지 않습니다. 로그인 후 연결 테스트를 실행해 주세요.');
    for(const job of Array.isArray(setupState.jobs)?setupState.jobs:[]){
      if(['queued','running'].includes(job.status)&&!installJobs.has(job.provider)){installJobs.set(job.provider,job);watchInstall(job.id||job.jobId,job.provider);}
    }
    renderSetup();providerStatus();
  }catch(error){setupMessage(error.message,true);}
  finally{$('refresh-setup').disabled=false;}
}
function renderSetup(){
  $('provider-install-list').replaceChildren();
  for(const provider of setupState?.providers||[]){
    const card=text('article','','provider-install-card');
    const loginCommand=typeof provider.loginCommand==='string'&&provider.loginCommand.trim()?provider.loginCommand:loginCommands[provider.id];
    const header=text('div','','provider-card-header');
    const identity=text('div','','provider-identity');
    identity.append(text('span',provider.name?.slice(0,1)||'A','provider-monogram'),text('h3',provider.name||provider.id));
    const current=installJobs.get(provider.id),working=current&&['queued','running'].includes(current.status);
    const checked=connectionChecks.get(provider.id);
    const badge=text('span',working?'설치 중':provider.installed?'설치됨':'설치 필요','install-status'+(provider.installed?' installed':''));
    header.append(identity,badge);card.append(header);
    card.append(text('p',current?.message||provider.message||(provider.installed?'이 PC에서 실행 도구를 찾았습니다.':'요약을 사용하려면 실행 도구를 설치해 주세요.'),'provider-description'));
    if(provider.id==='gemini')card.append(text('p','기존 개인용 Gemini CLI 로그인은 서비스 지원이 종료되었습니다. CLI 설치와 사용 가능한 계정·인증은 별개입니다.','provider-caution'));
    const actions=text('div','','provider-card-actions');
    if(!provider.installed){
      const install=text('button',working?'설치 중…':'설치하기','primary');
      install.disabled=working||!provider.installable;
      install.onclick=()=>installProvider(provider.id);actions.append(install);
      if(!provider.installable&&provider.id==='node'){
        const link=text('a','Node.js 공식 다운로드','button-link');link.href='https://nodejs.org/';link.target='_blank';link.rel='noopener noreferrer';actions.append(link);
      }
    }
    if(loginCommand){
      const test=text('button',checked?.ok?'연결 다시 확인':'연결 테스트');
      test.disabled=!provider.installed||working||aiRequestRunning;
      test.onclick=()=>busyButton(test,()=>testProviderConnection(provider.id));actions.append(test);
      const use=text('button','요약에 사용');use.disabled=!provider.installed||working;
      use.onclick=()=>{ $('provider').value=provider.id;refreshSelect('provider');dirty=true;providerStatus();notice('요약에 사용할 AI를 바꿨습니다. 설정 저장을 눌러 적용하세요.');};actions.append(use);
    }
    card.append(actions);
    if(checked)card.append(text('p',checked.ok?'가상 메시지 응답 확인 완료':checked.message||'연결을 확인하지 못했습니다.','connection-result'+(checked.ok?' success':' error')));
    if(loginCommand){
      const login=text('details','','login-guide');login.append(text('summary','본인 계정으로 로그인하는 방법'));
      login.append(text('p','Windows 터미널에서 아래 명령을 실행하고 본인 인증을 마쳐 주세요. 비밀번호나 인증 코드는 이 프로그램에 입력하지 않습니다.'));
      const command=text('div','','login-command');command.append(text('code',loginCommand));
      const copy=text('button','명령 복사');copy.onclick=()=>busyButton(copy,async()=>{await navigator.clipboard.writeText(loginCommand);notice('로그인 명령을 복사했습니다.');});command.append(copy);login.append(command);card.append(login);
    }
    $('provider-install-list').append(card);
  }
  const save=text('button','AI 선택 저장','primary');save.id='save-ai-choice';save.onclick=()=>busyButton(save,()=>saveSettings('provider'));$('provider-install-list').append(save);
}
async function installProvider(provider){
  if(!token){setupMessage('프로그램 연결을 준비하고 있습니다. 잠시 후 다시 시도해 주세요.',true);return;}
  const available=setupState?.providers?.find(item=>item.id===provider);
  if(!available?.installable||installJobs.get(provider)?.status==='running')return;
  installJobs.set(provider,{provider,status:'queued',message:'공식 패키지 설치를 준비하고 있습니다.'});renderSetup();
  setupMessage('공식 패키지를 설치합니다. 설치 후 본인 계정 로그인과 연결 테스트가 필요합니다.');
  try{
    const started=await api('setup/install',{provider});
    const jobId=started.jobId||started.id;if(!jobId)throw Error('설치 작업 번호를 받지 못했습니다. 상태를 새로고침해 주세요.');
    installJobs.set(provider,{provider,id:jobId,status:'running',message:'설치 중입니다. 프로그램을 종료하지 말아 주세요.'});renderSetup();watchInstall(jobId,provider);
  }catch(error){installJobs.set(provider,{provider,status:'failed',message:error.message});setupMessage(error.message,true);renderSetup();}
}
async function watchInstall(id,provider,failures=0){
  try{
    const result=await getSetup('setup/job?id='+encodeURIComponent(id)),job=result.job||result;
    installJobs.set(provider,{...job,provider});renderSetup();
    if(['queued','running'].includes(job.status)){setTimeout(()=>watchInstall(id,provider),1500);return;}
    if(job.status==='succeeded'){setupMessage('설치를 마쳤습니다. 본인 계정으로 로그인한 뒤 연결 테스트를 실행해 주세요.');await refreshSetup();}
    else setupMessage(job.message||'설치하지 못했습니다. 상태를 확인하고 다시 시도해 주세요.',true);
  }catch(error){
    if(failures<4){setTimeout(()=>watchInstall(id,provider,failures+1),3000);return;}
    installJobs.set(provider,{id,provider,status:'unknown',message:'설치 진행 상태를 읽지 못했습니다. 상태 새로고침으로 다시 확인해 주세요.'});setupMessage(error.message,true);renderSetup();
  }
}
$('nav-settings').onclick=()=>page('settings');$('open-settings').onclick=()=>page('settings');$('refresh-setup').onclick=refreshSetup;
function updateSendControls(){
  const blocked=activeRoom&&sendOutcomes.get(activeRoom.id)?.delivery==='unknown';
  $('chat-send').disabled=!activeRoom||!$('chat-draft').value.trim()||sendPreparing||sendInFlight||aiRequestRunning||blocked;
  $('chat-send').textContent=sendPreparing?'전송 확인 중…':sendInFlight?'전송 중…':'직접 전송';
}
function invalidateSendPreview(){sendPreviewRequestId++;}
function renderSendOutcome(){
  const panel=$('send-outcome'),outcome=activeRoom?sendOutcomes.get(activeRoom.id):null;
  panel.replaceChildren();panel.hidden=!outcome;
  if(!outcome)return;
  panel.dataset.delivery=outcome.delivery;
  const labels={submitted:'카카오톡 전송 요청을 완료했습니다.',unknown:'전송 여부를 확인하지 못했습니다.',not_delivered:'전송하지 못했습니다.'};
  panel.append(text('strong',labels[outcome.delivery]||labels.unknown),text('p',outcome.message||''));
  if(outcome.delivery==='unknown'){
    panel.append(text('p','자동으로 다시 보내지 않습니다. 중복 전송을 막기 위해 실제 카카오톡 대화를 먼저 확인해 주세요.'));
    const acknowledge=text('button','카카오톡에서 확인했어요');
    acknowledge.onclick=()=>{if(!activeRoom||sendInFlight)return;sendOutcomes.delete(activeRoom.id);renderSendOutcome();updateSendControls();notice('자동으로 다시 보내지 않습니다. 필요한 경우 직접 전송에서 다시 시도해 주세요.');};
    panel.append(acknowledge);
  }
}
function historyContentKey(messages,attachments){return JSON.stringify([messages.map(m=>[m.id,m.sender,m.text,m.sentAt,m.fromMe,m.kind]),attachments.map(a=>[a.messageId,a.name,a.kind,a.size,a.expiresAt])]);}
function compareHistoryMessages(a,b){const at=Date.parse(a.sentAt||''),bt=Date.parse(b.sentAt||'');if(Number.isFinite(at)&&Number.isFinite(bt)&&at!==bt)return at-bt;const ai=String(a.id??''),bi=String(b.id??'');if(/^\d+$/.test(ai)&&/^\d+$/.test(bi)){const av=BigInt(ai),bv=BigInt(bi);return av<bv?-1:av>bv?1:0;}return ai.localeCompare(bi);}
async function quietRefreshRoom(roomId){
  if(!roomId||String(activeRoom?.id)!==String(roomId)||currentPage!=='summary'||document.visibilityState!=='visible'||quietHistoryBusy)return false;
  quietHistoryBusy=true;const requestId=++historyRequestId,oldKey=historyContentKey(historyMessages,historyAttachments),oldCursor=historyBefore;
  try{
    const result=await api('history',{roomId});
    if(String(activeRoom?.id)!==String(roomId)||requestId!==historyRequestId||currentPage!=='summary'||document.visibilityState!=='visible')return false;
    const latest=result.messages||[],latestIds=new Set(latest.map(m=>String(m.id))),firstLatest=latest[0],older=firstLatest?historyMessages.filter(m=>!latestIds.has(String(m.id))&&compareHistoryMessages(m,firstLatest)<0):historyMessages;
    historyMessages=[...older,...latest];historyBefore=oldCursor?oldCursor:older.length?null:result.next_before_id;const olderIds=new Set(older.map(m=>String(m.id))),freshAttachments=result.attachments||[],olderAttachments=historyAttachments.filter(a=>olderIds.has(String(a.messageId)));historyAttachments=[...olderAttachments,...freshAttachments];
    const newKey=historyContentKey(historyMessages,historyAttachments);historyCache.set(String(roomId),{messages:[...historyMessages],attachments:[...historyAttachments],before:historyBefore});if(newKey===oldKey)return false;
    const container=$('chat-messages'),oldTop=container.scrollTop,wasAtBottom=container.scrollHeight-container.scrollTop-container.clientHeight<64;
    $('chat-meta').textContent=`이 PC에 저장된 대화 · ${result.coverage?.storedLocally??historyMessages.length}개`;renderChat(false);container.scrollTop=wasAtBottom?container.scrollHeight:Math.min(oldTop,container.scrollHeight);return true;
  }catch{return false;}finally{quietHistoryBusy=false;const queued=queuedHistoryRead;queuedHistoryRead=null;if(queued&&String(activeRoom?.id)===String(queued.room.id))openRoom(queued.room,queued.before);}
}
setInterval(()=>{if(activeRoom)quietRefreshRoom(activeRoom.id);},5000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&activeRoom)quietRefreshRoom(activeRoom.id);});
async function sendCurrentDraft(){
  if(!activeRoom||!state||!token){notice('전송할 채팅방을 먼저 열어 주세요.');return;}
  if(sendPreparing||sendInFlight||aiRequestRunning)return;
  if(sendOutcomes.get(activeRoom.id)?.delivery==='unknown'){notice('실제 카카오톡 대화에서 전송 여부를 먼저 확인해 주세요.');return;}
  const roomId=String(activeRoom.id),sourceText=$('chat-draft').value;
  if(!sourceText.trim()){notice('전송할 내용을 입력해 주세요.');return;}
  if([...sourceText].length>2000||sourceText.includes('\0')){notice('직접 전송은 2,000자 이하의 본문만 지원합니다. 초안은 그대로 유지했습니다.');return;}
  invalidateSendPreview();const requestId=sendPreviewRequestId;sendPreparing=true;updateSendControls();notice('전송 정보를 확인하고 있습니다.');let outcome=null;
  try{
    const preview=await api('send-preview',{roomId,text:sourceText});
    if(requestId!==sendPreviewRequestId||String(activeRoom?.id)!==roomId||$('chat-draft').value!==sourceText)return;
    const expires=typeof preview.expiresAt==='number'?(preview.expiresAt<1e12?preview.expiresAt*1000:preview.expiresAt):Date.parse(preview.expiresAt);
    if(typeof preview.token!=='string'||!preview.token||String(preview.roomId)!==roomId||typeof preview.title!=='string'||!preview.title.trim()||typeof preview.text!=='string'||preview.text!==sourceText||!Number.isFinite(expires)||expires<=Date.now())throw Error('전송 정보를 확인하지 못했습니다. 초안을 확인한 뒤 다시 눌러 주세요.');
    if(requestId!==sendPreviewRequestId||String(activeRoom?.id)!==roomId||$('chat-draft').value!==sourceText)return;
    sendPreparing=false;sendInFlight=true;updateSendControls();notice('카카오톡에 전송하고 있습니다.');
    const response=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify({token:preview.token,replaceHint:preview.requiresHintReplacement===true})});let result;try{result=await response.json();}catch{result={};}
    const delivery=['submitted','unknown','not_delivered'].includes(result.delivery)?result.delivery:'unknown';outcome={delivery:(!response.ok&&delivery!=='not_delivered')?'unknown':delivery,message:typeof result.message==='string'?result.message:''};
    if(outcome.delivery==='submitted')outcome.message=outcome.message||'카카오톡에 전송을 요청했습니다. 상대방의 수신 여부는 실제 대화에서 확인해 주세요.';
    if(outcome.delivery==='not_delivered')outcome.message=outcome.message||'초안은 그대로 유지했습니다. 원인을 확인한 뒤 다시 시도할 수 있습니다.';
  }catch(error){if(sendInFlight)outcome={delivery:'unknown',message:'응답을 받지 못해 전송 여부를 알 수 없습니다. 초안은 그대로 유지했습니다.'};else notice('전송 준비를 완료하지 못했습니다. '+error.message);}
  finally{
    sendPreparing=false;sendInFlight=false;invalidateSendPreview();
    if(outcome){sendOutcomes.set(roomId,outcome);if(outcome.delivery==='submitted'&&String(activeRoom?.id)===roomId&&$('chat-draft').value===sourceText){$('chat-draft').value='';sessionDrafts.set(roomId,'');state.drafts=state.drafts||{};state.drafts[roomId]='';try{await api('save-draft',{roomId,text:''});}catch{}}
      if(String(activeRoom?.id)===roomId){renderSendOutcome();updateSendControls();}notice(outcome.delivery==='submitted'?'전송 요청을 마쳤습니다. 실제 대화에서 결과를 확인해 주세요.':outcome.delivery==='unknown'?'전송 여부를 확인하지 못했습니다. 실제 대화에서 확인해 주세요.':'전송하지 못했습니다. 초안은 유지했습니다.');
      await quietRefreshRoom(roomId);if(outcome.delivery==='submitted')setTimeout(()=>quietRefreshRoom(roomId),900);
    }else updateSendControls();
  }
}
$('chat-send').onclick=sendCurrentDraft;
$('chat-draft').addEventListener('compositionstart',()=>{draftComposing=true;});$('chat-draft').addEventListener('compositionend',()=>{draftComposing=false;});
$('chat-draft').addEventListener('keydown',event=>{if(event.key!=='Enter'||event.shiftKey||event.isComposing||draftComposing||event.keyCode===229)return;event.preventDefault();if(event.repeat)return;sendCurrentDraft();});
$('chat-draft').addEventListener('input',()=>{if(activeRoom){sessionDrafts.set(activeRoom.id,$('chat-draft').value);const generated=tutorialGeneratedDraft;if(generated?.roomId===activeRoom.id&&generated.text!==$('chat-draft').value)tutorialAction('draft-edited',generated.stamp);}invalidateSendPreview();updateSendControls();});

function updateSummaryControls(){
  const nextKey=[...chosen.keys()].sort().join('|');if(nextKey!==batchSelectionKey){batchSelectionKey=nextKey;if(!aiRequestRunning)$('batch-progress').textContent='';}
  for(const id of ['summarize-all','summarize-today','summarize-range'])$(id).disabled=aiRequestRunning||!chosen.size;
  for(const id of ['summarize-this-room','summarize-this-today','chat-generate'])$(id).disabled=aiRequestRunning||!activeRoom;
  for(const id of ['provider','save-ai-choice','select-all','clear-all','save-selection','summary-start','summary-end','room-scope','room-start','room-end'])if($(id))$(id).disabled=aiRequestRunning;
  for(const [id,control] of customSelects)if(['provider','room-scope'].includes(id))control.trigger.disabled=aiRequestRunning;
  for(const button of $('selected-rooms').querySelectorAll('button'))button.disabled=aiRequestRunning;
  $('batch-target').textContent=chosen.size?`${chosen.size}개 채팅방: ${[...chosen.values()].slice(0,3).map(r=>r.title).join(', ')}${chosen.size>3?' 외 '+(chosen.size-3)+'개':''}`:'선택한 채팅방이 없습니다. 왼쪽 목록에서 요약할 방을 체크하세요.';
}
function renderConversationRooms(){
  const list=$('chat-rooms'),query=$('chat-search').value.trim().toLocaleLowerCase();list.replaceChildren();
  const matches=rooms.filter(r=>r.title.toLocaleLowerCase().includes(query));
  for(const r of matches.slice(0,chatRoomLimit)){const button=text('button','','conversation-room'+(activeRoom?.id===r.id?' current':''));button.setAttribute('aria-label',r.title+' 대화 보기');button.setAttribute('aria-pressed',String(activeRoom?.id===r.id));button.append(text('span',r.title,'room-title'),text('span',`${r.memberCount?r.memberCount+'명 · ':''}${r.readable?'읽기 준비됨':'처음 읽을 때 연결 확인'}`,'room-meta'));button.onclick=()=>openRoom(r);list.append(button);}
  if(!matches.length)list.append(text('p',rooms.length?'검색 결과가 없습니다.':'새로고침으로 채팅방을 불러오세요.','empty-small'));
  if(matches.length>chatRoomLimit){const more=text('button','채팅방 더 보기','list-more');more.onclick=()=>{chatRoomLimit+=100;renderConversationRooms();};list.append(more);}
}
function renderBatchReports(){
  if(!batchHasRun)return;$('batch-result-heading').hidden=false;$('batch-result-meta').textContent=batchResultMeta;const target=$('batch-reports');target.replaceChildren();
  for(const id of batchResultIds){const r=state.reports?.[id];if(!r)continue;const article=text('article','','report');article.append(text('h3',r.title),text('p',({all:'전체 대화',today:'오늘 대화',range:'기간 대화'})[r.scope]||'대화','report-sub'),text('div',r.error?(errors[r.error]||r.error):r.summary||'요약 내용이 없습니다.','summary-text'));const view=text('button','대화와 요약 보기');view.onclick=()=>openBriefing({roomId:r.id,title:r.title,summary:r.summary||'',checkedAt:r.checkedAt},true);article.append(view);target.append(article);}
}
$('chat-search').oninput=()=>{chatRoomLimit=100;renderConversationRooms();if($('chat-search').value.trim())tutorialAction('room-search',tutorialBegin('room-search'));};
$('chat-refresh-list').onclick=()=>busy('chat-refresh-list',async()=>{const result=await api('rooms');rooms=result.rooms||[];roomsLoaded=true;renderRooms();notice(rooms.length+'개 채팅방을 불러왔습니다.');});
$('workspace-settings').onclick=()=>page('settings');

async function loadConversationRooms(){
  roomsLoading=true;$('chat-rooms').replaceChildren(text('p','채팅방 목록을 불러오고 있습니다.','empty-small'));
  try{const result=await api('rooms');rooms=result.rooms||[];roomsLoaded=true;renderRooms();}catch(error){$('chat-rooms').replaceChildren(text('p',error.message,'empty-small'));const retry=text('button','다시 불러오기','list-more');retry.onclick=loadConversationRooms;$('chat-rooms').append(retry);}finally{roomsLoading=false;}
}
