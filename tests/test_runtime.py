import os
import subprocess
import sys
import time
from pathlib import Path
import pytest
from backend.chemistry import parse_result,parse_xyz
from backend.jobs import JobStore
from test_chemistry import WATER

LOG='xtb version 99.2.3\n*** convergence criteria satisfied after 5 iterations ***\nTOTAL ENERGY -5.0 Eh\n'

def test_job_artifact_bytes_and_hashes_survive_windows_newlines(tmp_path,monkeypatch):
    import hashlib
    import backend.jobs as jobs
    # Exercise Windows' default text newline translation on every test host.
    original_open=Path.open
    def windows_open(path,mode='r',*args,**kwargs):
        if 'w' in mode and 'b' not in mode and kwargs.get('newline') is None:
            kwargs['newline']='\r\n'
        return original_open(path,mode,*args,**kwargs)
    monkeypatch.setattr(Path,'open',windows_open)
    monkeypatch.setattr(jobs,'ENGINE',Path(sys.executable))
    store=JobStore(tmp_path)
    try:
        xyz=WATER.replace('water','水 molecule')
        jid=store.submit(dict(xyz=xyz,charge=0,uhf=0,mode='sp'))
        job=store.get(jid)
        original=(store.directory(jid)/'input.xyz').read_bytes()
        normalized=(store.directory(jid)/'engine.xyz').read_bytes()
        assert original==xyz.encode('utf-8')
        assert hashlib.sha256(original).hexdigest()==job['input_sha256']
        assert b'\r' not in normalized
        assert hashlib.sha256(normalized).hexdigest()==job['normalized_sha256']
    finally:store.close()

def test_unknown_version_retains_scientific_checks():
    atoms=parse_xyz(WATER)
    assert parse_result(LOG,'sp','99.2.3',None,atoms)['valid']
    assert not parse_result(LOG+'SCC NOT CONVERGED','sp','99.2.3',None,atoms)['valid']
    assert not parse_result(LOG.replace('*** convergence criteria satisfied after 5 iterations ***',''),'sp','99.2.3',None,atoms)['valid']
    assert not parse_result(LOG,'opt','99.2.3',None,atoms)['valid']

def test_unknown_version_can_queue_and_missing_engine_cannot(tmp_path,monkeypatch):
    import backend.jobs as jobs
    monkeypatch.setattr(jobs,'ENGINE',Path(sys.executable))
    with __import__('unittest.mock',fromlist=['patch']).patch.object(jobs.subprocess,'run',return_value=subprocess.CompletedProcess([],0,LOG,'')):
        s=JobStore(tmp_path/'ok')
    try:
        assert s.version=='99.2.3' and s.engine_error is None
        assert s.get(s.submit(dict(xyz=WATER,charge=0,uhf=0,mode='sp')))['status']=='queued'
    finally:s.close()
    monkeypatch.setattr(jobs,'ENGINE',tmp_path/'absent.exe')
    s=JobStore(tmp_path/'absent')
    try:
        assert s.engine_error
        with pytest.raises(ValueError):s.submit(dict(xyz=WATER,charge=0,uhf=0,mode='sp'))
    finally:s.close()

@pytest.mark.parametrize('exitcode,converged,status',[(0,True,'succeeded'),(3,True,'failed'),(0,False,'failed')])
def test_native_worker_result_and_exit_validation(tmp_path,monkeypatch,exitcode,converged,status):
    import backend.jobs as jobs
    monkeypatch.setattr(jobs,'ENGINE',Path(sys.executable))
    s=JobStore(tmp_path/'state with spaces')
    try:
        xyz=WATER.replace('water','水 molecule')
        jid=s.submit(dict(xyz=xyz,charge=0,uhf=0,mode='sp'))
        assert (s.directory(jid)/'input.xyz').read_bytes()==xyz.encode('utf-8')
        j=s.get(jid);j['command']=[sys.executable,'-c',f'print({(LOG if converged else "TOTAL ENERGY -5.0 Eh")!r});raise SystemExit({exitcode})'];s.save(j);s.start()
        for _ in range(400):
            j=s.get(jid)
            if j['status'] in jobs.TERMINAL:break
            time.sleep(.025)
        assert j['status']==status,j
        if exitcode:assert str(exitcode) in j['error']
        assert (s.directory(jid)/'final.xyz').exists()==(status=='succeeded')
    finally:s.close()

def test_owned_tree_cancellation_and_parent_death(tmp_path):
    # Exercise the real OS boundary on both CI operating systems, including grandchildren.
    runner=Path(__file__).resolve().parents[1]/'backend/runner.py'
    child=tmp_path/'child.py';marker=tmp_path/'heartbeat'
    child.write_text('import pathlib,time,sys\np=pathlib.Path(sys.argv[1])\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(.03)\n')
    owner=tmp_path/'owner.py'
    owner.write_text('import subprocess,sys,os,time\np=subprocess.Popen([sys.executable,sys.argv[1],str(os.getpid()),sys.executable,sys.argv[2],sys.argv[3]],start_new_session=True)\nwhile True:time.sleep(1)\n')
    unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
    p=subprocess.Popen([sys.executable,str(owner),str(runner),str(child),str(marker)])
    try:
        for _ in range(200):
            if marker.exists():break
            time.sleep(.025)
        assert marker.exists()
        p.kill();p.wait();time.sleep(.3)
        before=marker.read_text();time.sleep(.2)
        assert marker.read_text()==before
        assert unrelated.poll() is None
    finally:
        if p.poll() is None:p.kill();p.wait()
        unrelated.kill();unrelated.wait()

@pytest.mark.parametrize('running',[False,True])
def test_cancel_only_owned_job(tmp_path,monkeypatch,running):
    import backend.jobs as jobs
    monkeypatch.setattr(jobs,'ENGINE',Path(sys.executable))
    s=JobStore(tmp_path)
    unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
    try:
        jid=s.submit(dict(xyz=WATER,charge=0,uhf=0,mode='sp'))
        j=s.get(jid);j['command']=[sys.executable,'-c','import time;print("ready",flush=True);time.sleep(30)'];s.save(j)
        if running:
            s.start()
            for _ in range(200):
                if (s.directory(jid)/'output.log').stat().st_size:break
                time.sleep(.025)
            assert (s.directory(jid)/'output.log').stat().st_size
        s.cancel(jid)
        for _ in range(200):
            if s.get(jid)['status']=='cancelled':break
            time.sleep(.025)
        assert s.get(jid)['status']=='cancelled'
        assert unrelated.poll() is None
        assert not (s.directory(jid)/'final.xyz').exists()
    finally:s.close();unrelated.kill();unrelated.wait()


def test_native_launcher_http_and_owner_shutdown(tmp_path):
    import json,shutil,socket,urllib.request,venv
    root=Path(__file__).resolve().parents[1]
    stage=tmp_path/'native launch 空格'
    stage.mkdir()
    for name in ('backend','tools','config'):
        shutil.copytree(root/name,stage/name,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(root/'frontend/dist',stage/'frontend/dist')
    shutil.copy(root/'Start-Windows.cmd',stage/'Start-Windows.cmd')
    venv.EnvBuilder(system_site_packages=True,with_pip=False).create(stage/'.venv')
    import site
    packages=(stage/'.venv/Lib/site-packages' if os.name=='nt' else stage/'.venv/lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'site-packages')
    (packages/'verification.pth').write_text('\n'.join(site.getsitepackages()))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=dict(os.environ,WORKBENCH_PORT=str(port),WORKBENCH_NO_BROWSER='1')
    command=([os.environ.get('COMSPEC','cmd.exe'),'/c',str(stage/'Start-Windows.cmd')]
        if os.name=='nt' else [sys.executable,str(stage/'tools/portable.py')])
    # Windows cmd is a wrapper; test killing the Python launcher below by
    # invoking its native entry directly after separately checking cmd's check.
    if os.name=='nt':
        check=subprocess.run([*command,'check'],cwd=stage,env=env,capture_output=True,text=True,timeout=15)
        assert check.returncode==0,check.stdout+check.stderr
        assert json.loads(check.stdout)['platform']=='Windows'
        command=[sys.executable,str(stage/'tools/portable.py')]
    with (stage/'startup.txt').open('w') as output:
        p=subprocess.Popen(command,cwd=stage,env=env,stdout=output,stderr=output)
        try:
            for _ in range(200):
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/config',timeout=.2) as r:
                        config=json.load(r)
                    break
                except OSError:
                    if p.poll() is not None:raise AssertionError((stage/'startup.txt').read_text())
                    time.sleep(.05)
            else:raise AssertionError('HTTP did not become ready')
            assert config['backend']=='local' and config['backends'][1]['available'] is False
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=2) as r:assert r.status==200
        finally:p.kill();p.wait()
    for _ in range(100):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))!=0:break
        time.sleep(.05)
    else:raise AssertionError('API survived launcher exit')
