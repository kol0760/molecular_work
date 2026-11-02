import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.jobs import JobStore
from test_chemistry import WATER
HEAD={'X-Workbench':'1'}

def wait(c,j):
    for _ in range(200):
        r=c.get('/api/jobs/'+j).json()
        if r['status'] not in ['queued','running']: return r
        time.sleep(.03)
    raise AssertionError('job did not finish')

def submit(c,mode='sp'):
    r=c.post('/api/jobs',json={'xyz':WATER,'charge':0,'uhf':0,'mode':mode},headers=HEAD)
    assert r.status_code==201,r.text
    return r.json()['id']

def test_security_and_validation(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        assert c.get('/api/config',headers={'Host':'evil.test'}).status_code==400
        assert c.post('/api/jobs',json={},headers={'Origin':'https://evil.test',**HEAD}).status_code==403
        assert c.post('/api/jobs',json={}).status_code==403
        assert c.post('/api/jobs',json={},headers={**HEAD,'Sec-Fetch-Site':'cross-site'}).status_code==403
        assert c.post('/api/jobs',json={'xyz':WATER,'charge':0,'uhf':1,'mode':'sp'},headers=HEAD).status_code==422
        assert c.post('/api/jobs',json={'xyz':WATER,'charge':0,'uhf':0,'mode':'shell'},headers=HEAD).status_code==422
        assert c.post('/api/jobs',content='x'*140000,headers={**HEAD,'Content-Type':'application/json'}).status_code==413
        assert c.get('/api/jobs/bad/files/secret').status_code==404

def test_real_jobs_and_snapshot(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        sp=submit(c); opt=submit(c,'opt'); other=submit(c)
        a,b=wait(c,sp),wait(c,opt)
        assert a['status']==b['status']=='succeeded',(a,b)
        assert a['finished']<=b['started']
        assert a['xyz']==WATER
        assert b['result']['geometry_converged'] is True
        assert c.get(f'/api/jobs/{opt}/files/final.xyz').status_code==200
        assert c.get(f'/api/jobs/{opt}/files/provenance.json').json()['version']==c.get('/api/config').json()['version']
        assert c.get(f'/api/jobs/{opt}/files/input.xyz').text==WATER
        assert len(c.get('/api/jobs').json())==3
        assert wait(c,other)['status']=='succeeded'
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        assert c.get('/api/jobs/'+sp).json()['status']=='succeeded'
        assert len(c.get('/api/jobs').json())==3

def test_queued_cancel_and_restart(tmp_path):
    s=JobStore(tmp_path)
    j=s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'})
    assert s.cancel(j)['status']=='cancelled'
    k=s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'})
    s.close()
    s=JobStore(tmp_path)
    assert s.get(k)['status']=='interrupted'
    assert s.get(j)['status']=='cancelled'
    s.close()

def test_no_second_worker(tmp_path):
    s=JobStore(tmp_path)
    with pytest.raises(RuntimeError): JobStore(tmp_path)
    s.close()

def test_engine_matches_direct_cli(tmp_path):
    import subprocess
    from backend.chemistry import parse_result,parse_xyz
    with TestClient(create_app(tmp_path/'state'),base_url='http://127.0.0.1:8765') as c:
        for mode in ['sp','opt']:
            j=wait(c,submit(c,mode))
            direct=tmp_path/mode;direct.mkdir()
            (direct/'engine.xyz').write_text((tmp_path/'state'/j['id']/'engine.xyz').read_text())
            p=subprocess.run(j['command'],cwd=direct,env=JobStore.env(),capture_output=True,text=True,timeout=20)
            assert p.returncode==0
            out=(direct/'xtbopt.xyz').read_text() if mode=='opt' else None
            r=parse_result(p.stdout+p.stderr,mode,j['version'],out,parse_xyz(WATER))
            assert r['valid']
            assert j['result']['energy_hartree']==pytest.approx(r['energy_hartree'],abs=1e-10)
            if mode=='opt':assert parse_xyz(j['result']['final_xyz'])==parse_xyz(out)

def large_xyz():
    return '200\nPublic synthetic hydrogen grid for lifecycle testing\n'+''.join(f'H {i%10*1.5} {(i//10)%10*1.5} {i//100*1.5}\n' for i in range(200))

def test_running_cancellation_owns_only_engine(tmp_path):
    import subprocess
    s=JobStore(tmp_path)
    unrelated=subprocess.Popen([__import__('sys').executable,'-c','import time;time.sleep(20)'])
    try:
        jid=s.submit({'xyz':large_xyz(),'charge':0,'uhf':0,'mode':'opt'});s.start()
        for _ in range(400):
            with s.mu:
                if s.process is not None and s.process.poll() is None and (s.directory(jid)/'output.log').stat().st_size>0:
                    p=s.process;break
            time.sleep(.005)
        else:raise AssertionError('No live engine')
        s.cancel(jid)
        for _ in range(400):
            if s.get(jid)['status'] in ('cancelled','failed','succeeded'):break
            time.sleep(.005)
        assert s.get(jid)['status']=='cancelled'
        assert p.poll() is not None
        assert unrelated.poll() is None
        assert not (s.directory(jid)/'final.xyz').exists()
    finally:s.close();unrelated.terminate();unrelated.wait()

def test_runtime_and_real_nonconvergence(tmp_path,monkeypatch):
    from backend.jobs import LIMITS
    s=JobStore(tmp_path/'time')
    try:
        monkeypatch.setitem(LIMITS,'runtime_seconds',0)
        jid=s.submit({'xyz':large_xyz(),'charge':0,'uhf':0,'mode':'opt'});s.start()
        for _ in range(400):
            j=s.get(jid)
            if j['status']=='failed':break
            time.sleep(.005)
        assert j['status']=='failed' and 'Runtime' in j['error']
    finally:s.close()
    monkeypatch.setitem(LIMITS,'runtime_seconds',600)
    s=JobStore(tmp_path/'scc')
    try:
        jid=s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'})
        j=s.get(jid);j['command'][-1]='1';s.save(j);s.start()
        for _ in range(400):
            j=s.get(jid)
            if j['status']=='failed':break
            time.sleep(.005)
        assert j['status']=='failed' and j['result']['valid'] is False
        assert j['result']['final_xyz'] is None
    finally:s.close()

def test_recovery_includes_older_jobs_beyond_history_window(tmp_path):
    s=JobStore(tmp_path)
    jid=s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'})
    # Seed newer terminal history cheaply; the real old job must remain lifecycle-visible.
    with s.mu:
        template=s.get(jid)
        import json,uuid
        for _ in range(501):
            j={**template,'id':uuid.uuid4().hex,'status':'cancelled'}
            s.db.execute('INSERT INTO jobs VALUES (?,?)',(j['id'],json.dumps(j)))
        s.db.commit()
    s.close()
    s=JobStore(tmp_path)
    try:assert s.get(jid)['status']=='interrupted'
    finally:s.close()

def test_startup_recovers_persisted_running_and_queued_without_rerun(tmp_path):
    import json,sqlite3
    s=JobStore(tmp_path)
    a=s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'})
    b=s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'})
    s.close()
    # Simulate a process dying before it could persist shutdown states.
    with sqlite3.connect(tmp_path/'jobs.sqlite') as db:
        for jid,status in [(a,'running'),(b,'queued')]:
            j=json.loads(db.execute('SELECT data FROM jobs WHERE id=?',(jid,)).fetchone()[0]);j['status']=status
            db.execute('UPDATE jobs SET data=? WHERE id=?',(json.dumps(j),jid))
    s=JobStore(tmp_path)
    try:
        assert s.get(a)['status']==s.get(b)['status']=='interrupted'
        assert not (s.directory(a)/'final.xyz').exists()
    finally:s.close()

def test_queue_is_bounded_and_can_free_cancelled_slot(tmp_path):
    s=JobStore(tmp_path)
    try:
        ids=[s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'}) for _ in range(20)]
        with pytest.raises(ValueError,match='Queue is full'):s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'})
        s.cancel(ids[0])
        assert s.get(s.submit({'xyz':WATER,'charge':0,'uhf':0,'mode':'sp'}))['status']=='queued'
    finally:s.close()
