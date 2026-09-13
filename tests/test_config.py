"""Offline behavior tests. All credentials and resources below are synthetic."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / 'tools/generate_config.py'
if GENERATOR.exists():
    spec = importlib.util.spec_from_file_location('generate_config', GENERATOR)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
else:
    gen = None


def config(scenes=False):
    return {
        'ownSyncBox': {'host': 'syncbox.test.local', 'token': 'synthetic-test-bearer-94',
                       'certificateFingerprint': '0123456789abcdef' * 4, 'input': 4},
        'optionalScenes': {'enabled': scenes,
                          'ownBridge': {'host': 'bridge.test.local', 'applicationKey': 'synthetic-test-key-85',
                                        'certificateFingerprint': 'fedcba9876543210' * 4},
                          'scenes': {k: str(uuid.uuid5(uuid.NAMESPACE_DNS, 'fixture.' + k)) for k in ('cinema', 'pause', 'read')},
                          'readGuard': {'sensorResourceId': str(uuid.uuid5(uuid.NAMESPACE_DNS, 'fixture.sensor')),
                                        'start': '20:00', 'end': '06:00', 'luxThreshold': 2000}}
    }


def shortcuts(document):
    return {s['name']: s for c in document['categories'] for s in c['shortcuts']}


def js(code, response=None, variables=None, hour=21, nested=None, fail_nested=False, nested_status='success'):
    harness = r'''
const fs=require('fs'), vm=require('vm');
const p=JSON.parse(fs.readFileSync(0,'utf8'));
const vars=Object.assign({hsr_request_nonce:'fixture-nonce',hsr_last_cinema_ms:'0',hsr_scene_index:'-1'},p.variables);
const calls=[];let result=null;let aborted=false;
class Clock extends Date {constructor(){super(1000000);}getHours(){return p.hour;}getMinutes(){return 0;}static now(){return 1000000;}}
const env={response:p.response, Date:Clock, getVariable:k=>{if(!(k in vars))throw Error('missing');return vars[k];},
setVariable:(k,v)=>vars[k]=v,setResult:r=>result=JSON.parse(r),logEvent:()=>{},abort:()=>{aborted=true;throw Error('synthetic-abort');},
executeShortcut:id=>{calls.push(id);if(p.fail_nested)throw Error('network');return {result:JSON.stringify(p.nested || {ok:true,ready:true}),status:p.nested_status};}};
try {vm.runInNewContext(p.code,env,{timeout:1000});} catch(error){if(error.message!=='synthetic-abort')throw error;}
process.stdout.write(JSON.stringify({result,calls,aborted,variables:vars}));
'''
    p = subprocess.run(['node', '-e', harness], input=json.dumps(dict(code=code, response=response,
                       variables=variables or {}, hour=hour, nested=nested, fail_nested=fail_nested, nested_status=nested_status)),
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(gen, 'fresh standalone generator has not been implemented')

    def test_core_schema_and_input_four(self):
        doc = gen.build_import(config())
        self.assertEqual((doc['version'], doc['compatibilityVersion']), (91, 90))
        contract = json.loads((ROOT / 'contract.json').read_text())
        lookup = shortcuts(doc)
        self.assertEqual(len(lookup), len(contract['shortcuts']))
        for kind, ref in contract['shortcuts'].items():
            s = lookup[ref['name']]
            self.assertEqual(s['id'], ref['id'])
            self.assertEqual(s['delay'], 0)
            self.assertEqual(s['repetitionInterval'], 0)
            self.assertFalse(s['waitForInternet'])
            self.assertEqual(s['responseHandling']['successOutput'], 'none')
        probe = lookup[contract['shortcuts']['PROBE']['name']]
        self.assertEqual(probe['url'], 'https://syncbox.test.local/api/v1/')
        self.assertEqual(probe['authentication'], 'bearer')
        self.assertEqual(probe['authToken'], config()['ownSyncBox']['token'])
        self.assertFalse(probe['acceptAllCertificates'])
        self.assertFalse(probe['followRedirects'])
        start = lookup[contract['shortcuts']['START']['name']]
        self.assertEqual(json.loads(start['bodyContent']), {'syncActive': True, 'mode': 'video', 'hdmiSource': 'input4'})
        stop = lookup[contract['shortcuts']['STOP']['name']]
        self.assertEqual(json.loads(stop['bodyContent']), {'syncActive': False})
        self.assertEqual(start['method'], 'PUT')
        self.assertEqual(stop['url'], 'https://syncbox.test.local/api/v1/execution')

    def test_config_rejects_unsafe_or_missing_core(self):
        for key, value in [('host', 'http://host'), ('host', 'https://host'), ('host', 'host/path'),
                           ('host', 'host:443'), ('host', 'x\r\nInjected: yes'), ('host', '{{variable}}'),
                           ('host', 'box.invalid'), ('host', '999.999.999.999'), ('token', ''),
                           ('token', 'REPLACE_WITH_YOUR_TOKEN'), ('token', 'abc\nheader'),
                           ('token', '{{variable}}'), ('token', 'YOUR_SYNC_BOX_TOKEN'), ('host', 'fe80::1%eth0'), ('certificateFingerprint', ''),
                           ('certificateFingerprint', 'a' * 64), ('certificateFingerprint', 'a' * 63),
                           ('certificateFingerprint', 'zz' * 32), ('input', 0), ('input', 5), ('input', True), ('input', '4')]:
            with self.subTest(key=key, value=value):
                c = config(); c['ownSyncBox'][key] = value
                with self.assertRaises(ValueError): gen.build_import(c)
        c=config(); del c['ownSyncBox']['token']
        with self.assertRaises(ValueError): gen.build_import(c)
        c=config(); c['ownSyncBox']['typo'] = 'never silently ignore'
        with self.assertRaises(ValueError): gen.build_import(c)

    def test_all_inputs_and_ipv6_are_encoded_safely(self):
        for input_number in range(1,5):
            c=config();c['ownSyncBox']['input']=input_number;c['ownSyncBox']['host']='2001:db8::2'
            lookup=shortcuts(gen.build_import(c))
            self.assertEqual(lookup['Hue Relay - Probe']['url'],'https://[2001:db8::2]/api/v1/')
            self.assertEqual(json.loads(lookup['Hue Relay - Start']['bodyContent'])['hdmiSource'],'input'+str(input_number))

    def test_disabled_scenes_have_no_network_and_complete_with_nonce(self):
        c=config(); c['optionalScenes']={'enabled':False}
        doc=gen.build_import(c)
        for s in shortcuts(doc).values():
            if s['name'] in ('Hue Relay - Probe','Hue Relay - Start','Hue Relay - Stop'): continue
            self.assertEqual(s['executionType'],'scripting')
            self.assertFalse(s.get('url'))
            execution=js(s['codeOnPrepare'])
            self.assertEqual(execution['calls'],[])
            self.assertEqual(execution['result']['nonce'],'fixture-nonce')
            self.assertTrue(execution['result']['ok'])
            self.assertFalse(execution['result']['ready'])

    def test_probe_readiness_and_failures(self):
        s=shortcuts(gen.build_import(config()))['Hue Relay - Probe']
        payload={'execution':{'syncActive':False,'mode':'video','hdmiActive':True,'hdmiSource':'input4'},
                 'hdmi':{'input4':{'status':'linked'},'videoSyncSupported':True,'contentSpecs':'3840 x 2160 @ 60'}}
        response={'statusCode':200,'body':json.dumps(payload)}
        r=js(s['codeOnSuccess'],response)['result']
        self.assertTrue(r['ok']); self.assertTrue(r['ready']); self.assertFalse(r['active'])
        for mutate in ('wrong_source','unlinked','unsupported','no_dimensions','powersave'):
            q=copy.deepcopy(payload)
            if mutate=='wrong_source': q['execution']['hdmiSource']='input1'
            if mutate=='unlinked': q['hdmi']['input4']['status']='unlinked'
            if mutate=='unsupported': q['hdmi']['videoSyncSupported']=False
            if mutate=='no_dimensions': q['hdmi']['contentSpecs']='0x0@0'
            if mutate=='powersave': q['execution']['mode']='powersave'
            self.assertFalse(js(s['codeOnSuccess'],{'statusCode':200,'body':json.dumps(q)})['result']['ready'])
        for r in ({'statusCode':200,'body':''},{'statusCode':500,'body':json.dumps(payload)},None):
            self.assertFalse(js(s['codeOnSuccess'],r)['result']['ok'])
        self.assertFalse(js(s['codeOnFailure'])['result']['ok'])

    def test_start_stop_empty_2xx_success_and_failure_callbacks(self):
        lookup=shortcuts(gen.build_import(config()))
        for kind in ('Start','Stop'):
            s=lookup['Hue Relay - '+kind]
            for status in (200,201,204):
                r=js(s['codeOnSuccess'],{'statusCode':status,'body':''})['result']
                self.assertTrue(r['ok']); self.assertEqual(r['nonce'],'fixture-nonce')
                self.assertEqual(r['kind'],kind.upper())
            self.assertFalse(js(s['codeOnSuccess'],{'statusCode':302,'body':''})['result']['ok'])
            self.assertFalse(js(s['codeOnFailure'])['result']['ok'])

    def test_optional_scene_security_and_validation(self):
        doc=gen.build_import(config(True)); lookup=shortcuts(doc)
        for s in lookup.values():
            if s.get('url','').startswith('https://bridge.test.local'):
                self.assertFalse(s['acceptAllCertificates'])
                self.assertEqual(s['certificateFingerprint'],config(True)['optionalScenes']['ownBridge']['certificateFingerprint'])
                self.assertEqual(s['headers'],[{'key':'hue-application-key','value':'synthetic-test-key-85'}])
        recall=lookup['Hue Relay - Read Recall']
        self.assertEqual(json.loads(recall['bodyContent']),{'recall':{'action':'active'}})
        self.assertIn(config(True)['optionalScenes']['scenes']['read'],recall['url'])
        for section,key,bad in [('ownBridge','host','http://bad'),('ownBridge','applicationKey',''),
                                ('ownBridge','certificateFingerprint',''),('scenes','read','../bad'),
                                ('readGuard','sensorResourceId',''),('readGuard','start','25:00'),
                                ('readGuard','end','20:00'),('readGuard','luxThreshold',-1),
                                ('readGuard','luxThreshold',float('nan'))]:
            c=config(True); c['optionalScenes'][section][key]=bad
            with self.subTest(section=section,key=key):
                with self.assertRaises(ValueError): gen.build_import(c)

    def test_read_guard_sensor_window_and_recent_cinema(self):
        s=shortcuts(gen.build_import(config(True)))['Hue Relay - Read Check']
        def reading(level,valid=True): return {'statusCode':200,'body':json.dumps({'data':[{'light':{'light_level_valid':valid,'light_level':level}}]})}
        self.assertTrue(js(s['codeOnSuccess'],reading(2000))['result']['ready'])
        self.assertFalse(js(s['codeOnSuccess'],reading(2001))['result']['ready'])
        self.assertFalse(js(s['codeOnSuccess'],reading(100),hour=12)['result']['ready'])
        self.assertFalse(js(s['codeOnSuccess'],reading(100),variables={'hsr_last_cinema_ms':'999000'})['result']['ready'])
        self.assertTrue(js(s['codeOnSuccess'],reading(100,False))['result']['ready'])
        self.assertTrue(js(s['codeOnFailure'])['result']['ready'])
        self.assertFalse(js(s['codeOnFailure'],hour=12)['result']['ready'])
        c=config(True);c['optionalScenes']['readGuard'].update(start='07:00',end='19:00')
        day=shortcuts(gen.build_import(c))['Hue Relay - Read Check']
        self.assertTrue(js(day['codeOnSuccess'],reading(100),hour=12)['result']['ready'])
        self.assertFalse(js(day['codeOnSuccess'],reading(100),hour=21)['result']['ready'])

    def test_scene_requests_remain_top_level_and_skips_abort_after_result(self):
        lookup=shortcuts(gen.build_import(config(True)))
        self.assertEqual(len(lookup),9)
        for name in ('Cinema','Pause'):
            scene=lookup['Hue Relay - '+name]
            self.assertEqual(scene['executionType'],'app')
            self.assertEqual(scene['method'],'PUT')
            day=js(scene['codeOnPrepare'],hour=12)
            self.assertTrue(day['aborted']);self.assertTrue(day['result']['ok'])
            self.assertEqual(day['result']['nonce'],'fixture-nonce')
            night=js(scene['codeOnPrepare'])
            self.assertFalse(night['aborted'])
        read=lookup['Hue Relay - Read']
        self.assertEqual(read['executionType'],'scripting')
        self.assertFalse(js(read['codeOnPrepare'])['result']['ready'])
        for enabled in (False,True):
            for shortcut in shortcuts(gen.build_import(config(enabled))).values():
                for field in ('codeOnPrepare','codeOnSuccess','codeOnFailure'):
                    for forbidden in ('executeShortcut','enqueueShortcut','sendHttpRequest','sendIntent'):
                        self.assertNotIn(forbidden,shortcut.get(field,''))

    def test_cycle_is_one_ungated_put_with_correct_scene_order(self):
        lookup=shortcuts(gen.build_import(config(True)))
        cycle=lookup['Hue Relay - Cycle']
        self.assertEqual(cycle['method'],'PUT')
        self.assertIn('{{hsr_cycle_target}}',cycle['url'])
        scenes=config(True)['optionalScenes']['scenes']
        for i, scene in enumerate(('cinema','pause','read')):
            run=js(cycle['codeOnPrepare'],hour=12,variables={'hsr_scene_index':str(i-1)})
            self.assertEqual(run['variables']['hsr_cycle_target'],scenes[scene])
            self.assertFalse(run['aborted']);self.assertEqual(run['calls'],[])
        recall=lookup['Hue Relay - Cinema']
        self.assertTrue(js(recall['codeOnSuccess'],{'statusCode':204,'body':''})['result']['ok'])
        self.assertFalse(js(recall['codeOnSuccess'],{'statusCode':200,'body':json.dumps({'errors':[{'description':'synthetic error'}]})})['result']['ok'])

    def test_cycle_target_and_index_are_local_while_shared_scene_state_is_persisted(self):
        document=gen.build_import(config(True))
        self.assertEqual({v['key'] for v in document['variables']},
                         {'hsr_scene_index', 'hsr_last_cinema_ms'})
        cycle=shortcuts(document)['Hue Relay - Cycle']
        self.assertTrue(cycle['url'].endswith('/scene/{{hsr_cycle_target}}'))
        execution=js(cycle['codeOnPrepare']+'\n'+cycle['codeOnSuccess'],
                     {'statusCode':204,'body':''}, variables={'hsr_scene_index':'0'})
        self.assertEqual(execution['variables']['hsr_cycle_target'],config(True)['optionalScenes']['scenes']['pause'])
        self.assertEqual(execution['variables']['hsr_cycle_index'],'1')
        self.assertEqual(execution['variables']['hsr_scene_index'],'1')
        self.assertTrue(execution['result']['ok'])

    def test_fail_closed_sensor_setting(self):
        c=config(True);c['optionalScenes']['readGuard']['readFailOpen']=False
        s=shortcuts(gen.build_import(c))['Hue Relay - Read Check']
        self.assertFalse(js(s['codeOnFailure'])['result']['ready'])
        self.assertFalse(js(s['codeOnSuccess'],{'statusCode':200,'body':'invalid'})['result']['ready'])

    def test_public_template_rejected_and_no_original_references(self):
        with self.assertRaises(ValueError): gen.build_import(json.loads((ROOT/'config.example.json').read_text()))
        combined='\n'.join(p.read_text() for p in [GENERATOR,*sorted((ROOT/'templates').glob('*.js'))])
        for forbidden in ('hf_native_nonce','dev.codex.huescenerelay','work/hue-sync','deepcopy','private/'):
            self.assertNotIn(forbidden,combined)
        c=config();c['ownSyncBox']['token']='special-sensitive-fixture'
        with tempfile.TemporaryDirectory() as directory:
            cfg=Path(directory)/'config.local.json';cfg.write_text(json.dumps(c))
            p=subprocess.run(['python3',str(GENERATOR),str(cfg)],text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            out=Path(p.stdout.strip()); self.assertEqual(out.parent,(Path(directory)/'generated').resolve())
            self.assertNotIn(c['ownSyncBox']['token'],p.stdout+p.stderr)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(out.parent.stat().st_mode),0o700)
            with zipfile.ZipFile(out) as z:
                self.assertEqual(z.namelist(),['shortcuts.json'])
                self.assertIn(c['ownSyncBox']['token'],z.read('shortcuts.json').decode())

    def test_every_enabled_callback_has_matching_kind_and_nonce(self):
        lookup=shortcuts(gen.build_import(config(True)))
        for kind, reference in json.loads((ROOT/'contract.json').read_text())['shortcuts'].items():
            shortcut=lookup[reference['name']]
            if shortcut['executionType']!='app': continue
            result=js(shortcut['codeOnFailure'])['result']
            self.assertEqual(result['kind'],kind);self.assertEqual(result['nonce'],'fixture-nonce')
            self.assertFalse(result['active'])
            if kind!='READ_CHECK': self.assertFalse(result['ok'])

    def test_generated_directory_cannot_redirect_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);target=parent/'elsewhere';target.mkdir()
            (parent/'generated').symlink_to(target,target_is_directory=True)
            with self.assertRaises(ValueError): gen.write_import(gen.build_import(config()),parent/'config.local.json')
            self.assertEqual(list(target.iterdir()),[])

    def test_errors_never_echo_input_values(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg=Path(directory)/'config.local.json';c=config();secret='SENSITIVE\nvalue';c['ownSyncBox']['token']=secret
            cfg.write_text(json.dumps(c))
            p=subprocess.run(['python3',str(GENERATOR),str(cfg)],text=True,capture_output=True)
            self.assertNotEqual(p.returncode,0); self.assertNotIn('SENSITIVE',p.stdout+p.stderr)
            self.assertFalse((Path(directory)/'generated').exists())

if __name__ == '__main__': unittest.main()
