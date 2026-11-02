"""Single-worker durable queue. No request controls an executable or filesystem path."""
import fcntl
import hashlib
import shutil
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from .chemistry import parse_result,validate_request

ENGINE=Path(os.environ.get('WORKBENCH_XTB') or shutil.which('xtb') or '/nonexistent/xtb').resolve()
RUNNER=Path(__file__).with_name('runner.py').resolve()
TERMINAL={'succeeded','failed','cancelled','interrupted'}
LIMITS={'atoms':300,'xyz_bytes':131072,'threads':1,'runtime_seconds':600,'optimization_cycles':200,'queued_jobs':20,'log_bytes':20*1024*1024,'memory_bytes':2*1024**3}

def now(): return time.time()

class JobStore:
    def __init__(self,root):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lockfile=(self.root/'worker.lock').open('a')
        try: fcntl.flock(self.lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lockfile.close(); raise RuntimeError('Another workbench already owns this state directory.')
        self.mu=threading.RLock(); self.stop=threading.Event(); self.wakeup=threading.Event()
        self.thread=None; self.process=None; self.active=None; self.cancelled=set()
        self.db=sqlite3.connect(self.root/'jobs.sqlite',check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)');self.db.commit()
        self.version=None;self.engine_error=None
        try:
            v=subprocess.run([str(ENGINE),'--version'],capture_output=True,text=True,timeout=5,env=self.env())
            match=re.search(r'xtb version\s+(\d+\.\d+\.\d+)',v.stdout+v.stderr)
            if v.returncode or not match: raise RuntimeError('Cannot identify xTB version')
            self.version=match[1]
            if self.version!='6.6.1': self.engine_error='This parser is verified only for xTB 6.6.1.'
        except Exception as e: self.engine_error=str(e)
        for j in self.list():
            if j['status'] not in TERMINAL:
                j.update(status='interrupted',finished=now(),error='Service restarted; job was not rerun.')
                self.save(j)
    @staticmethod
    def env():
        # No user xTB control files or inherited OpenMP/thread settings.
        return {'PATH':str(ENGINE.parent)+':/usr/bin:/bin','HOME':'/nonexistent','LC_ALL':'C','OMP_NUM_THREADS':'1','OMP_STACKSIZE':'64M','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1'}
    def directory(self,jid):
        if not re.fullmatch(r'[0-9a-f]{32}',jid): raise KeyError(jid)
        return self.root/jid
    def get(self,jid):
        self.directory(jid)
        with self.mu: row=self.db.execute('SELECT data FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row: raise KeyError(jid)
        return json.loads(row[0])
    def list(self):
        with self.mu: rows=self.db.execute('SELECT data FROM jobs ORDER BY rowid DESC').fetchall()
        return [json.loads(r[0]) for r in rows]
    def save(self,j):
        with self.mu:
            self.db.execute('INSERT INTO jobs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(j['id'],json.dumps(j,allow_nan=False)));self.db.commit()
            p=self.directory(j['id'])/'provenance.json'
            tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(j,indent=2,allow_nan=False));tmp.replace(p)
    def submit(self,data):
        validated=validate_request(data['xyz'],data['charge'],data['uhf'])
        if data['mode'] not in ('sp','opt'):raise ValueError('Choose single point or optimization.')
        if self.engine_error: raise ValueError(self.engine_error)
        with self.mu:
            if len([j for j in self.list() if j['status']=='queued'])>=20:raise ValueError('Queue is full (20 waiting jobs).')
            jid=uuid.uuid4().hex;d=self.directory(jid);d.mkdir(mode=0o700)
            (d/'input.xyz').write_text(data['xyz']);(d/'engine.xyz').write_text(validated['normalized_xyz']);(d/'output.log').touch()
            command=[str(ENGINE),'engine.xyz','--gfn','2','--chrg',str(data['charge']),'--uhf',str(data['uhf']),'--acc','1.0','--iterations','250']
            if data['mode']=='opt':command+=['--opt','normal','--cycles','200']
            j={**data,'id':jid,'created':now(),'started':None,'finished':None,'status':'queued','version':self.version,'executable':str(ENGINE),'command':command,'limits':LIMITS,'method':'GFN2-xTB','phase':'gas','coordinate_unit':'angstrom','input_sha256':hashlib.sha256(data['xyz'].encode()).hexdigest(),'normalized_sha256':hashlib.sha256(validated['normalized_xyz'].encode()).hexdigest(),'result':None,'error':None,'returncode':None}
            self.save(j);self.wakeup.set();return jid
    def start(self):
        self.thread=threading.Thread(target=self.work,name='xtb-worker',daemon=True);self.thread.start()
    def signal_owned(self):
        p=self.process
        if p is not None and p.poll() is None:
            try:
                if os.getpgid(p.pid)==p.pid:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    def cancel(self,jid):
        with self.mu:
            j=self.get(jid)
            if j['status']=='queued':j.update(status='cancelled',finished=now(),error='Cancelled before execution.');self.save(j)
            elif j['status']=='running':
                self.cancelled.add(jid)
                if self.active==jid:self.signal_owned()
            return self.get(jid)
    def work(self):
        while not self.stop.is_set():
            with self.mu:
                queued=[j for j in reversed(self.list()) if j['status']=='queued']
                j=queued[0] if queued else None
                if j:
                    self.active=j['id'];j.update(status='running',started=now());self.save(j)
            if not j:
                self.wakeup.wait(.25);self.wakeup.clear();continue
            try:self.run(j)
            except Exception as e:
                with self.mu:
                    self.signal_owned()
                    if self.process:self.process.wait(timeout=5)
                    j.update(status='failed',finished=now(),error=f'Engine execution failed: {e}');self.save(j)
            finally:
                with self.mu:self.process=None;self.active=None;self.cancelled.discard(j['id'])
    def run(self,j):
        d=self.directory(j['id']);reason=None
        with (d/'output.log').open('wb') as log:
            with self.mu:
                if self.stop.is_set() or j['id'] in self.cancelled:
                    j.update(status='interrupted' if self.stop.is_set() else 'cancelled',finished=now());self.save(j);return
                self.process=subprocess.Popen([sys.executable,str(RUNNER),str(os.getpid()),*j['command']],cwd=d,env=self.env(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,shell=False)
                p=self.process
            while p.poll() is None:
                with self.mu:
                    if self.stop.is_set():reason='Service stopped.';self.signal_owned()
                    elif j['id'] in self.cancelled:reason='Cancelled by user.';self.signal_owned()
                    elif now()-j['started']>LIMITS['runtime_seconds']:reason='Runtime limit exceeded.';self.signal_owned()
                    elif (d/'output.log').stat().st_size>=LIMITS['log_bytes']:reason='Log size limit exceeded.';self.signal_owned()
                time.sleep(.025)
            p.wait()
        with self.mu:
            logtext=(d/'output.log').read_text(errors='replace')
            out=(d/'xtbopt.xyz').read_text(errors='replace') if (d/'xtbopt.xyz').exists() else None
            result=parse_result(logtext,j['mode'],j['version'],out,validate_request(j['xyz'],j['charge'],j['uhf'])['atoms'])
            if self.stop.is_set(): status='interrupted'
            elif j['id'] in self.cancelled:status='cancelled'
            else:status='succeeded' if p.returncode==0 and result['valid'] and not reason else 'failed'
            if status!='succeeded':result['final_xyz']=None;result['valid']=False
            if status=='succeeded' and j['mode']=='opt':(d/'final.xyz').write_text(result['final_xyz'])
            if status=='succeeded' and j['mode']=='sp':(d/'final.xyz').write_text((d/'engine.xyz').read_text())
            j.update(status=status,finished=now(),returncode=p.returncode,result=result,error=reason or (result['reason'] if status=='failed' else None));self.save(j)
    def close(self):
        self.stop.set();self.wakeup.set()
        if self.thread:self.thread.join(timeout=10)
        with self.mu:
            for j in self.list():
                if j['status'] not in TERMINAL:j.update(status='interrupted',finished=now(),error='Service stopped; job was not rerun.');self.save(j)
            self.db.close();fcntl.flock(self.lockfile,fcntl.LOCK_UN);self.lockfile.close()
