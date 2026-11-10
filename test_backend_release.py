"""Offline release checks: use dummy DPAPI fixtures, never account data or AI."""
import json
import os
import tempfile
import unittest
import io
from pathlib import Path
from unittest.mock import patch
import win32crypt
import app
import providers
import runtime_paths
import setup_service


class ReleaseBackendTests(unittest.TestCase):
    def test_install_verification_rejects_old_or_mixed_files(self):
        import hashlib
        import worker_entry
        from version import APP_VERSION
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as name:
            root = Path(name)
            sample = root / 'component.bin'
            sample.write_bytes(b'new-component')
            manifest = {'version': APP_VERSION, 'files': {'component.bin': hashlib.sha256(sample.read_bytes()).hexdigest()}}
            (root / 'install-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            self.assertTrue(worker_entry.verify_install(root, APP_VERSION))
            sample.write_bytes(b'old-component')
            self.assertFalse(worker_entry.verify_install(root, APP_VERSION))
            self.assertFalse(worker_entry.verify_install(root, 'older-version'))
            sample.unlink()
            self.assertFalse(worker_entry.verify_install(root, APP_VERSION))

    def test_worker_uses_utf8_even_when_console_defaults_to_cp949(self):
        import subprocess
        import sys
        script = '''import sys, json, runpy
from unittest.mock import patch
sys.stdout.reconfigure(encoding="cp949")
sys.stderr.reconfigure(encoding="cp949")
sys.argv = ["worker_entry.py", "--catalog-worker"]
def fake_worker(*args, **kwargs):
    print(json.dumps({"text": "한글 💕 🙂"}, ensure_ascii=False))
with patch("runpy.run_path", side_effect=fake_worker):
    runpy.run_module("worker_entry", run_name="__main__")
'''
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', script],
            cwd=Path(__file__).resolve().parent, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=15, creationflags=0x08000000)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        self.assertEqual(json.loads(result.stdout.decode('utf-8')), {'text': '한글 💕 🙂'})

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_dpapi_migration_preserves_original_and_existing_destination(self):
        source, destination = self.root / 'old.dpapi', self.root / 'new.dpapi'
        raw = win32crypt.CryptProtectData(b'{"fixture":true}', 'test', None, None, None, 0)
        source.write_bytes(raw)
        self.assertTrue(runtime_paths._copy_dpapi(source, destination, 10000))
        self.assertEqual(source.read_bytes(), raw)
        self.assertEqual(destination.read_bytes(), raw)
        self.assertFalse(runtime_paths._copy_dpapi(source, destination, 10000))
        self.assertFalse(list(self.root.glob('*.migrate-*')))

    def test_custom_runtime_never_imports_account_data(self):
        target = self.root / 'fixture-profile'
        with patch.dict(os.environ, {'CHATBRIEF_DATA_DIR': str(target)}), \
             patch.multiple(runtime_paths, DATA_ROOT=target, PRIVATE_DIR=target/'private',
                 READER_PRIVATE=target/'reader-private', AI_WORKSPACE=target/'ai-workspace'), \
             patch.object(runtime_paths, '_private_acl') as acl, \
             patch.object(runtime_paths, '_copy_dpapi') as copy:
            runtime_paths.ensure_runtime()
            self.assertTrue((target/'.chatbrief-data').is_file())
            self.assertTrue((target/'ai-workspace/AGENTS.md').is_file())
            acl.assert_called_once_with(target)
            copy.assert_not_called()

    def test_unowned_existing_folder_is_not_repermissioned(self):
        (self.root/'unrelated.txt').write_text('unrelated', encoding='utf-8')
        with patch.object(runtime_paths, 'DATA_ROOT', self.root), patch.object(runtime_paths, '_private_acl') as acl:
            with self.assertRaises(RuntimeError):
                runtime_paths.ensure_runtime()
            acl.assert_not_called()
        self.assertEqual((self.root/'unrelated.txt').read_text(), 'unrelated')

    def test_frozen_workers_are_explicit_modes(self):
        worker = self.root/'ChatBriefWorker.exe'
        worker.touch()
        with patch.object(app.runner.sys, 'frozen', True, create=True), \
             patch.object(app.runner.sys, 'executable', str(self.root/'ChatBrief.exe')):
            self.assertEqual(app.runner.worker_command(), [str(worker), '--reader-worker'])
            self.assertEqual(app.runner.worker_command(app.BASE/'bridge_worker.py')[-1], '--catalog-worker')
            worker.unlink()
            with self.assertRaises(FileNotFoundError):
                app.runner.worker_command()
            self.assertEqual(app.runner._run_request({'op':'status'})['error'], 'WORKER_EXECUTABLE_MISSING')

    def test_install_command_is_fixed_registry_and_no_shell(self):
        node = self.root/'node.exe'
        shim = self.root/'npm.cmd'
        script = self.root/'node_modules/npm/bin/npm-cli.js'
        script.parent.mkdir(parents=True)
        script.write_text('// fixture', encoding='utf-8')
        with patch.object(setup_service.shutil, 'which', side_effect=lambda name: str(node if name=='node.exe' else shim)):
            command = setup_service.npm_command('codex')
            self.assertEqual(command[:2], [str(node), str(script)])
            self.assertIn('--ignore-scripts', command)
            self.assertIn('--registry=https://registry.npmjs.org', command)
            self.assertEqual(command[command.index('--prefix') + 1], str(providers.CLI_ROOT))
            self.assertEqual(command[-1], '@openai/codex')
            with self.assertRaises(ValueError):
                setup_service.npm_command('codex && anything')

    def test_bundled_node_npm_and_user_cli_prefix_are_used_without_system_path(self):
        bundle = self.root/'bundle'
        node = bundle/'runtime/node/node.exe'
        npm = bundle/'runtime/node/node_modules/npm/bin/npm-cli.js'
        node.parent.mkdir(parents=True)
        node.touch()
        npm.parent.mkdir(parents=True)
        npm.touch()
        prefix = self.root/'app-data/cli'
        package = prefix/'node_modules/@openai/codex/bin/codex.js'
        package.parent.mkdir(parents=True)
        package.touch()
        with patch.object(runtime_paths, 'BUNDLE_ROOT', bundle), \
             patch.object(runtime_paths, 'DATA_ROOT', self.root/'app-data'), \
             patch.object(providers, 'BUNDLE_ROOT', bundle), \
             patch.object(providers, 'CLI_ROOT', prefix), \
             patch.object(setup_service, 'BUNDLE_ROOT', bundle), \
             patch.object(setup_service.shutil, 'which', return_value=None):
            self.assertEqual(providers.node_executable(), str(node))
            self.assertEqual(providers.executable('codex'), [str(node), str(package)])
            command = setup_service.npm_command('codex')
            self.assertEqual(command[:2], [str(node), str(npm)])
            self.assertEqual(command[command.index('--prefix') + 1], str(prefix))

    def test_provider_process_path_includes_node_while_preserving_existing_path(self):
        node = self.root/'bundle/runtime/node/node.exe'
        node.parent.mkdir(parents=True)
        node.touch()
        with patch.object(providers, 'BUNDLE_ROOT', self.root/'bundle'), \
             patch.object(providers, 'CLI_ROOT', self.root/'user-cli'), \
             patch.object(providers, 'executable', return_value=[str(node), 'fixture.js']), \
             patch.object(providers.subprocess, 'Popen') as popen:
            popen.return_value.communicate.return_value = (b'{"summaries":[]}', b'')
            popen.return_value.returncode = 0
            # Reach the child environment construction without invoking a real CLI.
            with patch.object(providers.win32job, 'CreateJobObject', side_effect=RuntimeError('fixture stop')):
                try:
                    providers._summarize('codex', [], providers.INSTRUCTION)
                except RuntimeError:
                    pass
            env = popen.call_args.kwargs['env']
            self.assertEqual(env['PATH'].split(os.pathsep)[:2], [str(node.parent), str(self.root/'user-cli')])
            self.assertTrue(env['PATH'].endswith(os.environ.get('PATH', '')))

    def test_setup_api_requires_local_token_for_install(self):
        handler = object.__new__(app.Handler)
        handler.path = '/api/setup/install'
        body = b'{"provider":"codex"}'
        handler.rfile = io.BytesIO(body)
        handler.headers = {'Host': f'127.0.0.1:{app.PORT}', 'Content-Length': str(len(body))}
        with patch.object(handler, 'respond') as respond, patch.object(setup_service, 'install') as install:
            handler.do_POST()
            self.assertEqual(respond.call_args.args[0], 403)
            install.assert_not_called()
            handler.headers['X-Local-Token'] = app.TOKEN
            install.return_value = {'id': 'fixture', 'jobId': 'fixture', 'status': 'queued'}
            handler.do_POST()
            self.assertEqual(respond.call_args.args[0], 202)
            install.assert_called_once_with('codex')

    def test_setup_api_job_not_found_is_explicit(self):
        handler = object.__new__(app.Handler)
        handler.path = '/api/setup/job?id=missing'
        handler.headers = {'Host': f'127.0.0.1:{app.PORT}'}
        with patch.object(handler, 'respond') as respond:
            handler.do_GET()
            self.assertEqual(respond.call_args.args[0], 404)

    def test_ai_requests_are_serialized(self):
        providers.AI_LOCK.acquire()
        try:
            with self.assertRaises(ValueError):
                providers.summarize('codex', [])
        finally:
            providers.AI_LOCK.release()

    def test_claude_cold_install_official_wrapper_is_detected(self):
        node = self.root/'node.exe'
        shim = self.root/'npm/claude.cmd'
        wrapper = shim.parent/'node_modules/@anthropic-ai/claude-code/cli-wrapper.cjs'
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('// official wrapper fixture', encoding='utf-8')
        with patch.object(providers.shutil, 'which', side_effect=lambda name: str(node) if name=='node.exe' else str(shim) if name=='claude.cmd' else None), \
             patch.object(providers.Path, 'home', return_value=self.root/'empty-profile'), \
             patch.dict(os.environ, {'APPDATA':str(self.root/'empty-profile/AppData/Roaming')}):
            self.assertEqual(providers.executable('claude'), [str(node),str(wrapper)])
            legacy = wrapper.with_name('cli.js')
            legacy.write_text('// older CLI fixture', encoding='utf-8')
            self.assertEqual(providers.executable('claude'), [str(node),str(legacy)])

    def test_login_commands_use_detected_wrapper_and_powershell_quoting(self):
        prefix = ["C:/O'Brien folder/node.exe", 'C:/fixture/cli-wrapper.cjs']
        with patch.object(providers, 'executable', return_value=prefix):
            self.assertEqual(setup_service.login_command('claude'), "& 'C:/O''Brien folder/node.exe' 'C:/fixture/cli-wrapper.cjs' 'auth' 'login'")
            self.assertTrue(setup_service.login_command('codex').endswith(" 'login'"))
            self.assertEqual(setup_service.login_command('gemini'), "& 'C:/O''Brien folder/node.exe' 'C:/fixture/cli-wrapper.cjs'")
        with patch.object(providers, 'executable', return_value=None):
            self.assertIsNone(setup_service.login_command('claude'))

    def test_manual_incremental_cannot_advance_schedule_cursor(self):
        state = app.load_state.__globals__['STATE']
        fixture = self.root/'state.dpapi'
        collection = {'checkedAt': app.now(), 'rooms': [], 'scope': 'incremental'}
        with patch.object(app, 'STATE', fixture), patch.object(app, 'collect', return_value=collection), \
             patch.object(app, 'persist_report') as persist:
            prepared = app.load_state()
            prepared['selected'] = [{'id':'1','title':'일괄 대상'}]
            app.save_state(prepared)
            app.run_check(use_ai=True, scope='incremental', scheduled=False)
            self.assertFalse(persist.call_args.kwargs['advance'])
            app.run_check(use_ai=True, scope='incremental', scheduled=True)
            self.assertTrue(persist.call_args.kwargs['advance'])
        self.assertEqual(app.STATE, state)

    def _scope_state(self):
        state = app.load_state()
        state['selected'] = [{'id':'1', 'title':'일괄 대상'}]
        state['scheduleSelected'] = [{'id':'3', 'title':'예약 대상'}]
        return state

    def _scope_reader(self, calls):
        catalog = {'rooms': [{'id':'1','title':'일괄 대상'}, {'id':'2','title':'보고 있는 방'}, {'id':'3','title':'예약 대상'}]}
        def read(request, **_kwargs):
            calls.append(dict(request))
            if request['op'] == 'rooms':
                return catalog
            return {'messages':[{'id':'10', 'sentAt':app.now(), 'text':'가상 대화'}], 'next_before_id':None, 'coverage':{}}
        return read

    def _scope_handler(self, path, body):
        handler = object.__new__(app.Handler)
        handler.path = path
        encoded = json.dumps(body).encode()
        handler.rfile = io.BytesIO(encoded)
        handler.headers = {'Host':f'127.0.0.1:{app.PORT}', 'Content-Length':str(len(encoded)), 'X-Local-Token':app.TOKEN}
        return handler

    def test_tutorial_first_run_and_completion_preserve_other_settings(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            initial = self._scope_state()
            app.save_state(initial)
            handler = object.__new__(app.Handler)
            handler.path = '/api/state'
            handler.headers = {'Host': f'127.0.0.1:{app.PORT}'}
            with patch.object(handler, 'respond') as respond:
                handler.do_GET()
                self.assertEqual(respond.call_args.args[0], 200)
                self.assertFalse(respond.call_args.args[1]['tutorialSeen'])
            finish = self._scope_handler('/api/tutorial', {'action': 'finish'})
            with patch.object(finish, 'respond') as respond:
                finish.do_POST()
                self.assertEqual(respond.call_args.args[0], 200)
            saved = app.load_state()
            self.assertTrue(saved['tutorialSeen'])
            self.assertEqual(saved['selected'], initial['selected'])
            self.assertEqual(saved['scheduleSelected'], initial['scheduleSelected'])
            self.assertEqual(saved['provider'], initial['provider'])

    def test_tutorial_api_rejects_untrusted_fields_and_missing_token(self):
        handler = self._scope_handler('/api/tutorial', {'action':'finish', 'selected':[]})
        with patch.object(handler, 'respond') as respond, patch.object(app, 'save_state') as save:
            handler.do_POST()
            self.assertEqual(respond.call_args.args[0], 400)
            save.assert_not_called()
        handler = self._scope_handler('/api/tutorial', {'action':'dismiss'})
        handler.headers.pop('X-Local-Token')
        with patch.object(handler, 'respond') as respond, patch.object(app, 'save_state') as save:
            handler.do_POST()
            self.assertEqual(respond.call_args.args[0], 403)
            save.assert_not_called()

    def test_previous_tutorial_completion_does_not_hide_new_tutorial_version(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            initial = self._scope_state()
            initial.update(tutorialVersion='1', tutorialSeen=True)
            app.save_state(initial)
            handler = object.__new__(app.Handler)
            handler.path = '/api/state'
            handler.headers = {'Host': f'127.0.0.1:{app.PORT}'}
            with patch.object(handler, 'respond') as respond:
                handler.do_GET()
                returned = respond.call_args.args[1]
                self.assertEqual(returned['tutorialCurrentVersion'], app.TUTORIAL_VERSION)
                self.assertNotEqual(returned['tutorialVersion'], returned['tutorialCurrentVersion'])
                self.assertTrue(returned['tutorialSeen'])
            finish = self._scope_handler('/api/tutorial', {'action':'finish'})
            with patch.object(finish, 'respond'):
                finish.do_POST()
            self.assertEqual(app.load_state()['tutorialVersion'], app.TUTORIAL_VERSION)

    def test_single_viewed_room_summary_is_independent_of_bulk_and_schedule(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            app.save_state(self._scope_state())
            calls = []
            with patch.object(app, 'read_local', side_effect=self._scope_reader(calls)), \
                 patch.object(providers, 'summarize', return_value={'2':{'text':'단일 방 요약','tasks':[]}}) as summarize:
                result = app.run_check(use_ai=True, scope='all', room_id='2')
            self.assertEqual([room['id'] for room in summarize.call_args.args[1]], ['2'])
            self.assertEqual([request['target'] for request in calls if request['op']=='read'], ['2'])
            self.assertEqual(result['selected'], [{'id':'1','title':'일괄 대상'}])
            self.assertEqual(result['scheduleSelected'], [{'id':'3','title':'예약 대상'}])
            self.assertEqual(result['reports']['2']['summary'], '단일 방 요약')
            self.assertIsNone(result['reports']['2']['through'])

    def test_bulk_summary_uses_only_explicit_checked_rooms(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            app.save_state(self._scope_state())
            calls = []
            with patch.object(app, 'read_local', side_effect=self._scope_reader(calls)), \
                 patch.object(providers, 'summarize', return_value={'1':{'text':'일괄 요약','tasks':[]}}) as summarize:
                app.run_check(use_ai=True, scope='all')
            self.assertEqual([room['id'] for room in summarize.call_args.args[1]], ['1'])
            self.assertEqual([request['target'] for request in calls if request['op']=='read'], ['1'])

    def test_bulk_zero_selection_never_falls_back_to_viewed_report_or_schedule(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            state = self._scope_state()
            state['selected'] = []
            state['reports'] = {'2':{'id':'2','title':'보고 있는 방','summary':'기존 요약'}}
            app.save_state(state)
            with patch.object(app, 'collect') as collect, patch.object(providers, 'summarize') as summarize:
                with self.assertRaisesRegex(ValueError, '선택한 채팅방이 없습니다'):
                    app.run_check(use_ai=True, scope='all')
                collect.assert_not_called()
                summarize.assert_not_called()

    def test_explicit_bulk_snapshot_uses_requested_ids_without_saving_selection(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            app.save_state(self._scope_state())
            calls = []
            handler = self._scope_handler('/api/check', {'ai':True,'scope':'today','roomIds':['2']})
            with patch.object(app, 'read_local', side_effect=self._scope_reader(calls)), \
                 patch.object(providers, 'summarize', return_value={'2':{'text':'명시 요약','tasks':[]}}) as summarize, \
                 patch.object(handler, 'respond') as respond:
                handler.do_POST()
                self.assertEqual(respond.call_args.args[0], 200)
            state = app.load_state()
            self.assertEqual([r['id'] for r in summarize.call_args.args[1]], ['2'])
            self.assertEqual([r['id'] for r in state['selected']], ['1'])
            self.assertEqual([r['id'] for r in state['scheduleSelected']], ['3'])
            self.assertEqual(state['job']['targetIds'], ['2'])
            self.assertEqual(state['job']['scope'], 'today')
            self.assertEqual(state['reports']['2']['summary'], '명시 요약')

    def test_explicit_bulk_invalid_ids_never_reach_ai_or_read(self):
        bodies = [{'roomIds':[]}, {'roomIds':['2','2']}, {'roomIds':['unknown']},
                  {'roomIds':['4']}, {'roomIds':['2']*3001}, {'roomIds':None},
                  {'roomIds':['2'], 'roomId':'1'}, {'roomId':None}, {'roomIds':[2]}]
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            app.save_state(self._scope_state())
            for body in bodies:
                with self.subTest(body=str(body)[:80]):
                    calls = []
                    handler = self._scope_handler('/api/check', dict(body, ai=True))
                    with patch.object(app, 'read_local', side_effect=self._scope_reader(calls)), \
                         patch.object(providers, 'summarize') as summarize, patch.object(handler, 'respond') as respond:
                        handler.do_POST()
                        self.assertEqual(respond.call_args.args[0], 400)
                        summarize.assert_not_called()
                        self.assertFalse(any(r['op']=='read' for r in calls))

    def test_history_poll_reuses_attachment_tokens_without_leaking_urls(self):
        attachment = {'messageId':'1','kind':'photo','url':'https://talk.kakaocdn.net/file/fixture','name':'사진'}
        with patch.object(app, 'MEDIA', {}):
            urls = []
            for _ in range(3):
                handler = self._scope_handler('/api/history', {'roomId':'1'})
                with patch.object(app, 'read_local', return_value={'messages':[], '_attachments':[attachment.copy()]}), patch.object(handler, 'respond') as respond:
                    handler.do_POST()
                    self.assertEqual(respond.call_args.args[0], 200)
                    urls.append(respond.call_args.args[1]['attachments'][0]['url'])
            self.assertEqual(len(set(urls)), 1)
            self.assertTrue(urls[0].startswith('/media/'))
            self.assertEqual(len(app.MEDIA), 1)

    def test_history_attachment_tokens_remain_valid_at_cache_limit(self):
        first = {'messageId':'1','kind':'photo','url':'https://talk.kakaocdn.net/file/first'}
        new = {'messageId':'2','kind':'photo','url':'https://talk.kakaocdn.net/file/new'}
        cache = {'oldest':first, **{str(i):{'messageId':str(i+10)} for i in range(4999)}}
        handler = self._scope_handler('/api/history', {'roomId':'1'})
        with patch.object(app, 'MEDIA', cache), patch.object(app, 'read_local', return_value={'messages':[], '_attachments':[new, first]}), patch.object(handler, 'respond') as respond:
            handler.do_POST()
            for item in respond.call_args.args[1]['attachments']:
                self.assertIn(item['url'].removeprefix('/media/'), app.MEDIA)
            self.assertEqual(len(app.MEDIA), 5000)

    def test_execution_snapshot_survives_concurrent_selection_change(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            app.save_state(self._scope_state())
            def collect(**kwargs):
                self.assertEqual(kwargs['selected_override'], [{'id':'1','title':'일괄 대상'}])
                changed = app.load_state()
                changed['selected'] = []
                changed['scheduleSelected'] = []
                app.save_state(changed)
                return {'checkedAt':app.now(),'rooms':[{'id':'1','title':'일괄 대상','messages':[]}]}
            with patch.object(app, 'collect', side_effect=collect):
                result = app.run_check(use_ai=True, scope='all')
            self.assertIn('1', result['reports'])
            self.assertEqual(result['job']['targetIds'], ['1'])

    def test_settings_partial_updates_preserve_unrelated_fields_and_next_run(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            original = self._scope_state()
            original.update(enabled=True,time='09:00',autoTodos=True,nextRun='2099-01-01T09:00:00+09:00')
            app.save_state(original)
            updates = [{'selected':[]}, {'provider':'claude'}, {'autoTodos':False}, {'time':'09:00'}]
            for update in updates:
                before = app.load_state()
                handler = self._scope_handler('/api/settings', update)
                with patch.object(app, 'next_run') as next_run, patch.object(handler, 'respond') as respond:
                    handler.do_POST()
                    self.assertEqual(respond.call_args.args[0], 200)
                    next_run.assert_not_called()
                after = app.load_state()
                for field in ('selected','scheduleSelected','enabled','time','provider','autoTodos','nextRun'):
                    self.assertEqual(after[field], update.get(field,before[field]))
            handler = self._scope_handler('/api/settings', {'time':'10:00'})
            with patch.object(app, 'next_run', return_value='changed') as next_run, patch.object(handler,'respond'):
                handler.do_POST()
                next_run.assert_called_once_with('10:00')
            self.assertEqual(app.load_state()['nextRun'], 'changed')

    def test_settings_partial_invalid_or_busy_never_mutates_state(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            app.save_state(self._scope_state())
            original = app.load_state()
            for body in ({'enabled':1},{'autoTodos':'yes'},{'provider':[]},{'time':'25:00'},{'selected':None},{'unknown':True}):
                handler = self._scope_handler('/api/settings', body)
                with patch.object(handler,'respond') as respond:
                    handler.do_POST()
                    self.assertEqual(respond.call_args.args[0],400)
                self.assertEqual(app.load_state(), original)
            app.RUN_LOCK.acquire()
            try:
                handler = self._scope_handler('/api/settings', {'selected':[]})
                with patch.object(handler,'respond') as respond:
                    handler.do_POST()
                    self.assertEqual(respond.call_args.args[0],409)
            finally:
                app.RUN_LOCK.release()
            self.assertEqual(app.load_state(),original)

    def test_unchecked_viewed_room_can_generate_and_save_reply(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            app.save_state(self._scope_state())
            calls = []
            handler = self._scope_handler('/api/reply', {'roomId':'2','tone':'정중하게','context':''})
            with patch.object(app, 'read_local', side_effect=self._scope_reader(calls)), \
                 patch.object(providers, 'summarize', return_value={'2':{'text':'가상 답장','tasks':[]}}), \
                 patch.object(handler, 'respond') as respond:
                handler.do_POST()
                self.assertEqual(respond.call_args.args[0], 200)
            self.assertEqual(app.load_state()['drafts']['2'], '가상 답장')
            handler = self._scope_handler('/api/save-draft', {'roomId':'2','text':'수정한 가상 답장'})
            with patch.object(app, 'read_local', side_effect=self._scope_reader(calls)), patch.object(handler, 'respond') as respond:
                handler.do_POST()
                self.assertEqual(respond.call_args.args[0], 200)
            state = app.load_state()
            self.assertEqual(state['drafts']['2'], '수정한 가상 답장')
            self.assertEqual([r['id'] for r in state['selected']], ['1'])
            self.assertEqual([r['id'] for r in state['scheduleSelected']], ['3'])

    def test_invalid_current_room_cannot_generate_reply(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            app.save_state(self._scope_state())
            handler = self._scope_handler('/api/reply', {'roomId':'2','tone':'정중하게'})
            with patch.object(app, 'read_local', return_value={'rooms':[]}), \
                 patch.object(providers, 'summarize') as summarize, patch.object(handler, 'respond') as respond:
                handler.do_POST()
                self.assertEqual(respond.call_args.args[0], 400)
                summarize.assert_not_called()

    def test_clearing_bulk_selection_preserves_previously_created_report(self):
        with patch.object(app, 'STATE', self.root/'state.dpapi'):
            state = self._scope_state()
            state['reports'] = {'2':{'id':'2','title':'보고 있는 방','summary':'유지할 요약'}}
            app.save_state(state)
            handler = self._scope_handler('/api/settings', {'selected':[], 'scheduleSelected':state['scheduleSelected'], 'enabled':False,'time':'09:00','provider':'codex','autoTodos':False})
            with patch.object(handler, 'respond') as respond:
                handler.do_POST()
                self.assertEqual(respond.call_args.args[0], 200)
            result = app.load_state()
            self.assertEqual(result['selected'], [])
            self.assertEqual(result['reports']['2']['summary'], '유지할 요약')
            self.assertEqual(result['scheduleSelected'], state['scheduleSelected'])

    def test_collection_deadline_preserves_cursor_and_marks_partial(self):
        fixture = self.root/'state.dpapi'
        with patch.object(app, 'STATE', fixture):
            state = app.load_state()
            state['selected'] = [{'id':'1','title':'첫 방'}, {'id':'2','title':'둘째 방'}]
            app.save_state(state)
            response = {'messages': [{'id':'1','sentAt':app.now(),'text':'fixture'}], 'next_before_id':None, 'coverage':{}}
            with patch.object(app, 'read_local', return_value=response), \
                 patch.object(app.time, 'monotonic', side_effect=[0,0,1,181]):
                result = app.collect(scope='all')
            self.assertTrue(result['truncated'])
            self.assertTrue(result['rooms'][0]['truncated'])
            self.assertEqual(result['rooms'][1]['error'], 'COLLECTION_LIMIT')
            app.persist_report(result, {'1': {'text':'fixture summary','tasks':[]}}, advance=True)
            self.assertIsNone(app.load_state()['reports']['1']['through'])


if __name__ == '__main__':
    unittest.main()
