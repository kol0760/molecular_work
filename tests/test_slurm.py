"""Offline only: transport responses are fixtures, never a real SSH/Slurm call."""
import json
from pathlib import Path
import pytest
from backend.slurm import SlurmAdapter,Config,Unavailable,Unsafe,SSHTransport
from test_chemistry import WATER

class MockTransport:
    def __init__(self,responses=()):self.calls=[];self.responses=list(responses)
    def run(self,argv,data=b''):
        self.calls.append((argv,data))
        r=self.responses.pop(0)
        if isinstance(r,Exception):raise r
        return r

def config(**kw):
    d=dict(enabled=True,ssh_host_alias='test-cluster',remote_work_root='/scratch/workbench',partition='',account='',cpus=1,memory_mb=1024,time_minutes=10,xtb_executable='/opt/xtb/bin/xtb',environment_setup='export PATH=/opt/xtb/bin:/usr/bin:/bin',site_preamble='')
    return Config({**d,**kw})

def create(tmp_path,transport):return SlurmAdapter(config(),tmp_path,transport)
def submit(adapter):return adapter.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'opt'})
def row(j,state='COMPLETED',code='0:0',**kw):return f"{j['slurm_id']}|{kw.get('name',j['name'])}|{state}|{code}|{j['remote_dir']}|\n".encode()

def test_disabled_and_missing_never_call_transport(tmp_path):
    t=MockTransport()
    a=SlurmAdapter(Config.load(tmp_path/'missing.json'),tmp_path/'state',t)
    assert a.connection()['connected'] is False
    with pytest.raises(Unavailable):submit(a)
    assert t.calls==[]
    sample=Config(json.loads(Path('config/slurm.example.json').read_text()))
    assert not sample.ready
    with pytest.raises(Unavailable):SSHTransport(sample)
    assert not config(ssh_host_alias='').ready

@pytest.mark.parametrize('field,value', [('ssh_host_alias','-oProxyCommand=evil'),('remote_work_root','/scratch/../home'),('partition','x\n#SBATCH --nodes=99'),('account','$(evil)'),('cpus',True),('cpus',129),('memory_mb',0),('time_minutes',1441),('xtb_executable','xtb;evil')])
def test_invalid_config_fails_closed(field,value):
    assert not config(**{field:value}).ready

def test_submit_snapshot_and_argv(tmp_path):
    t=MockTransport([b'',b'12345\n']);a=create(tmp_path,t);j=submit(a)
    assert j['slurm_id']=='12345' and j['state']=='submitted'
    assert j['xyz']==WATER and j['version'] is None
    assert t.calls[1][0][0]=='sbatch' and '--parsable' in t.calls[1][0]
    assert '--ntasks=1' in t.calls[1][0] and '--cpus-per-task=1' in t.calls[1][0]
    payload=json.loads(t.calls[0][1]);assert '--opt normal' in payload['script']
    assert '__' not in payload['script'] and 'OMP_NUM_THREADS=1' in payload['script']
    assert (tmp_path/j['id']/'input.xyz').read_text()==WATER
    assert a.get(j['id'])==j
    with pytest.raises(Unsafe):a.get('../secret')

@pytest.mark.parametrize('reply',[b'warning\n1234\n',b'1234;othercluster\n',TimeoutError()])
def test_ambiguous_submission_persists_no_retry(tmp_path,reply):
    t=MockTransport([b'',reply]);a=create(tmp_path,t)
    with pytest.raises(Unsafe):submit(a)
    receipt=list(tmp_path.glob('*/receipt.json'))[0]
    assert json.loads(receipt.read_text())['state']=='submission_unknown'
    assert len(t.calls)==2

def test_identity_status_cancel_and_restart(tmp_path):
    t=MockTransport([b'',b'12345\n']);a=create(tmp_path,t);j=submit(a)
    t.responses=[row(j,'RUNNING')];assert a.status(j['id'])['state']=='RUNNING'
    t.responses=[row(j,'RUNNING',name='other')]
    with pytest.raises(Unsafe):a.cancel(j['id'])
    assert len(t.calls)==4
    t.responses=[row(j,'RUNNING'),b''];a.cancel(j['id'])
    assert t.calls[-1][0]==['scancel','--ctld','--me','--name='+j['name'],j['slurm_id']]
    assert SlurmAdapter(config(),tmp_path,t).get(j['id'])['cancel_requested']
    t.responses=[b''];assert a.status(j['id'])['state']=='UNKNOWN'

@pytest.mark.parametrize('name',['../input.xyz','receipt.json','engine.xyz','output.log/../../secret'])
def test_artifact_allowlist_before_transport(tmp_path,name):
    t=MockTransport([b'',b'12345\n']);a=create(tmp_path,t);j=submit(a)
    with pytest.raises(Unsafe):a.artifact(j['id'],name)
    assert len(t.calls)==2

def test_artifact_verified_identity_and_size(tmp_path):
    t=MockTransport([b'',b'12345\n']);a=create(tmp_path,t);j=submit(a)
    t.responses=[row(j),b'public log'];assert a.artifact(j['id'],'output.log')==b'public log'
    assert t.calls[-1][0][0]=='python3'
    t.responses=[row(j,name='other')]
    with pytest.raises(Unsafe):a.artifact(j['id'],'output.log')
    t.responses=[row(j),b'x'*(20*1024*1024+1)]
    with pytest.raises(Unsafe):a.artifact(j['id'],'output.log')

def test_completed_is_not_scientific_success(tmp_path):
    t=MockTransport([b'',b'12345\n']);a=create(tmp_path,t);j=submit(a)
    t.responses=[row(j),b'xtb version 6.6.1',b'no convergence',WATER.encode()]
    r=a.collect(j['id']);assert not r['result']['valid'] and r['state']=='failed'

def test_private_config_permissions_and_malformed(tmp_path):
    p=tmp_path/'admin.json';p.write_text(json.dumps(config().data));p.chmod(0o644)
    assert not Config.load(p).ready
    p.chmod(0o600);assert Config.load(p).ready
    p.write_text('[]');assert not Config.load(p).ready
    p.write_text('{bad json');assert not Config.load(p).ready

def test_stage_failure_never_submits(tmp_path):
    t=MockTransport([RuntimeError('mock staging error')]);a=create(tmp_path,t)
    with pytest.raises(Unsafe):submit(a)
    assert len(t.calls)==1
    assert json.loads(next(tmp_path.glob('*/receipt.json')).read_text())['state']=='staging_failed'

@pytest.mark.skip(reason='Recorded runtime logs intentionally excluded from source release; run real CLI comparison tests instead.')
def test_collect_uses_existing_public_water_fixture_only(tmp_path):
    root=Path('evidence');t=MockTransport([b'',b'12345\n']);a=create(tmp_path,t);j=submit(a)
    t.responses=[row(j),b'xtb version 6.6.1',(root/'direct-opt/output.log').read_bytes(),(root/'direct-opt/xtbopt.xyz').read_bytes()]
    r=a.collect(j['id']);assert r['result']['valid'] and r['state']=='succeeded'
    assert r['result']['energy_hartree']==pytest.approx(-5.070544443465)
    assert r['result']['geometry_converged'] is True

def test_unverified_version_and_nonzero_exit_never_success(tmp_path):
    t=MockTransport([b'',b'12345\n']);a=create(tmp_path,t);j=submit(a)
    t.responses=[row(j,code='1:0')]
    with pytest.raises(Unsafe):a.collect(j['id'])
    t.responses=[row(j),b'xtb version 6.7.0']
    with pytest.raises(Unsafe):a.collect(j['id'])

def test_ssh_argv_quoting_without_launching_ssh(monkeypatch):
    import backend.slurm as module
    import shlex
    captured=[]
    def no_launch(argv,**kw):
        captured.append((argv,kw));raise RuntimeError('offline transport boundary')
    monkeypatch.setattr(module.subprocess,'Popen',no_launch)
    payload=['python3','-c','print("quote\'s; $(touch /never)")','space value']
    with pytest.raises(RuntimeError):SSHTransport(config()).run(payload)
    argv,kw=captured[0]
    assert argv[:2]==['/usr/bin/ssh','-T'] and '-oStrictHostKeyChecking=yes' in argv
    assert argv[-2]=='test-cluster' and shlex.split(argv[-1])==payload
    assert kw['shell'] is False

def test_remote_helper_local_only_identity_symlink_and_size(tmp_path):
    import hashlib,subprocess,sys
    from backend.slurm_remote import REMOTE
    root=tmp_path/'remote';root.mkdir(mode=0o700);jid='a'*32
    xyz=WATER;sha=hashlib.sha256(xyz.encode()).hexdigest()
    args=[sys.executable,'-c',REMOTE]
    stage=subprocess.run([*args,'stage',str(root),jid,sha],input=json.dumps({'xyz':xyz,'script':'#!/bin/bash\ntrue\n'}).encode(),capture_output=True)
    assert stage.returncode==0
    job=root/jid;(job/'output.log').write_bytes(b'public fixture log')
    def read():return subprocess.run([*args,'read',str(root),jid,sha,'output.log'],capture_output=True)
    assert read().stdout==b'public fixture log'
    (job/'output.log').unlink();(job/'output.log').symlink_to(job/'engine.xyz')
    assert read().returncode!=0
    (job/'output.log').unlink()
    with (job/'output.log').open('wb') as f:f.truncate(20*1024*1024+1)
    assert read().returncode!=0
    (job/'engine.xyz').write_text('tampered');assert read().returncode!=0
    # A pre-existing job directory cannot be reused/overwritten.
    assert subprocess.run([*args,'stage',str(root),jid,sha],input=b'{}',capture_output=True).returncode!=0

def test_public_api_has_no_hpc_selection_or_admin_configuration(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        public=c.get('/api/config').json()
        assert not any(k in public for k in ('ssh_host_alias','remote_work_root','environment_setup','slurm'))
        data={'xyz':WATER,'charge':0,'uhf':0,'mode':'sp','backend':'slurm'}
        assert c.post('/api/jobs',json=data,headers={'X-Workbench':'1'}).status_code==422
        assert c.get('/api/jobs').json()==[]
