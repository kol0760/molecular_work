"""Admin-only Slurm scaffold. Not imported, instantiated or routed by the web app.
No SSH is attempted by configuration loading or construction of SlurmAdapter.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import subprocess
import time
import uuid
from .chemistry import validate_request,parse_result
from .slurm_remote import REMOTE

class Unavailable(RuntimeError):pass
class Unsafe(RuntimeError):pass

def token(value):return isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',value))
def absolute(value):
    return isinstance(value,str) and bool(re.fullmatch(r'/[A-Za-z0-9_./-]+',value)) and all(p not in ('','.','..') for p in value[1:].split('/'))

class Config:
    def __init__(self,data):self.data=data
    @classmethod
    def load(cls,path):
        try:
            p=Path(path)
            if p.is_symlink() or p.stat().st_uid!=os.getuid() or p.stat().st_mode&0o077:return cls({})
            return cls(json.loads(p.read_text()))
        except (OSError,ValueError):return cls({})
    @property
    def ready(self):
        d=self.data
        if not isinstance(d,dict):return False
        fields={'enabled','ssh_host_alias','remote_work_root','partition','account','cpus','memory_mb','time_minutes','xtb_executable','environment_setup','site_preamble'}
        return (set(d)==fields and d.get('enabled') is True and token(d.get('ssh_host_alias'))
            and absolute(d.get('remote_work_root')) and absolute(d.get('xtb_executable'))
            and all(d.get(k)=='' or token(d.get(k)) for k in ('partition','account'))
            and all(type(d.get(k)) is int and lo<=d[k]<=hi for k,lo,hi in [('cpus',1,128),('memory_mb',128,262144),('time_minutes',1,1440)])
            and isinstance(d.get('environment_setup'),str) and bool(d['environment_setup'].strip())
            and isinstance(d.get('site_preamble'),str)
            and all(len(d[k])<=8192 and '\x00' not in d[k] for k in ('environment_setup','site_preamble')))

class SSHTransport:
    """Explicit admin use only. Constructor validates config; run is the SSH boundary."""
    def __init__(self,config):
        if not config.ready:raise Unavailable('Slurm not connected: disabled or incomplete administrator configuration.')
        self.host=config.data['ssh_host_alias']
    def run(self,argv,data=b''):
        # SSH ultimately invokes a remote shell; quote every argv member once.
        command=['/usr/bin/ssh','-T','-oBatchMode=yes','-oStrictHostKeyChecking=yes','-oConnectTimeout=10','--',self.host,shlex.join(argv)]
        p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,shell=False)
        sel=selectors.DefaultSelector();out=bytearray();pending=memoryview(data);deadline=time.monotonic()+30
        sel.register(p.stdout,selectors.EVENT_READ)
        if pending:os.set_blocking(p.stdin.fileno(),False);sel.register(p.stdin,selectors.EVENT_WRITE)
        else:p.stdin.close()
        try:
            while sel.get_map():
                if time.monotonic()>deadline:raise Unsafe('SSH timeout; submission outcome may be unknown. Do not retry automatically.')
                for key,_ in sel.select(.1):
                    if key.fileobj is p.stdin:
                        n=os.write(p.stdin.fileno(),pending[:65536]);pending=pending[n:]
                        if not pending:sel.unregister(p.stdin);p.stdin.close()
                    else:
                        chunk=os.read(p.stdout.fileno(),65536)
                        if not chunk:sel.unregister(p.stdout)
                        out.extend(chunk)
                        if len(out)>21*1024*1024:raise Unsafe('Remote output exceeds limit.')
            if p.wait(timeout=1)!=0:raise Unsafe('Remote command failed; inspect cluster privately. Do not retry submission automatically.')
            return bytes(out)
        finally:
            sel.close()
            if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
            for stream in (p.stdin,p.stdout):
                if not stream.closed:stream.close()

class SlurmAdapter:
    def __init__(self,config,state_dir,transport=None):
        self.config=config;self.root=Path(state_dir);self.transport=transport
    def connection(self):
        return {'connected':False,'configured':self.config.ready,'enabled':self.config.data.get('enabled') is True if isinstance(self.config.data,dict) else False,
            'detail':'Not connected: offline scaffold; no remote health check performed.'}
    def require(self):
        if not self.config.ready:raise Unavailable('Slurm not connected: disabled or incomplete administrator configuration.')
        if self.transport is None:raise Unavailable('No administrator transport attached; public application cannot enable Slurm.')
    def directory(self,jid):
        if not isinstance(jid,str) or not re.fullmatch('[0-9a-f]{32}',jid):raise Unsafe('Invalid receipt ID.')
        p=self.root/jid
        if p.is_symlink():raise Unsafe('Unsafe local receipt directory.')
        return p
    def save(self,j):
        p=self.directory(j['id'])/'receipt.json';tmp=p.with_suffix('.tmp')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:json.dump(j,f,allow_nan=False)
        tmp.replace(p)
    def get(self,jid):
        p=self.directory(jid)/'receipt.json'
        if p.is_symlink():raise Unsafe('Unsafe receipt.')
        j=json.loads(p.read_text())
        d=self.config.data
        if j['id']!=jid or j['name']!='wb_'+jid or j['remote_dir']!=d.get('remote_work_root','')+'/'+jid or j['host']!=d.get('ssh_host_alias'):raise Unsafe('Receipt/config identity mismatch.')
        if j.get('slurm_id') is not None and not re.fullmatch(r'[1-9][0-9]{0,19}',j['slurm_id']):raise Unsafe('Invalid scheduler identity.')
        return j
    def remote(self,op,j,name=None,data=b''):
        argv=['python3','-c',REMOTE,op,self.config.data['remote_work_root'],j['id'],j['normalized_sha256']]
        if name:argv.append(name)
        return self.transport.run(argv,data)
    def script(self,data):
        d=self.config.data
        command=[d['xtb_executable'],'engine.xyz','--gfn','2','--chrg',str(data['charge']),'--uhf',str(data['uhf']),'--acc','1.0','--iterations','250']
        if data['mode']=='opt':command+=['--opt','normal','--cycles','200']
        script=(Path(__file__).resolve().parents[1]/'templates/slurm.sbatch.in').read_text()
        values={'SITE_PREAMBLE':d['site_preamble'],'ENVIRONMENT_SETUP':d['environment_setup'],'CPUS':str(d['cpus']),'XTB_VERSION_COMMAND':shlex.join([d['xtb_executable'],'--version']),'XTB_COMMAND':shlex.join(command)}
        # Replace only template tokens, never reinterpret administrator shell text.
        return re.sub(r'__([A-Z_]+)__',lambda m:values[m[1]],script)
    def submit(self,data):
        self.require()
        if set(data)!={'xyz','charge','uhf','mode'} or data['mode'] not in ('sp','opt'):raise Unsafe('Only fixed xTB input fields are accepted.')
        v=validate_request(data['xyz'],data['charge'],data['uhf']);d=self.config.data
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        jid=uuid.uuid4().hex;p=self.directory(jid);p.mkdir(mode=0o700)
        (p/'input.xyz').write_text(data['xyz']);(p/'engine.xyz').write_text(v['normalized_xyz'])
        j={**data,'id':jid,'name':'wb_'+jid,'host':d['ssh_host_alias'],'remote_dir':d['remote_work_root']+'/'+jid,'normalized_sha256':hashlib.sha256(v['normalized_xyz'].encode()).hexdigest(),'slurm_id':None,'state':'staging','version':None,'cancel_requested':False,'result':None,'created':time.time(),'method':'GFN2-xTB','phase':'gas','coordinate_unit':'angstrom','resources':{k:d[k] for k in ('cpus','memory_mb','time_minutes','partition','account')},'input_sha256':hashlib.sha256(data['xyz'].encode()).hexdigest(),'script_sha256':hashlib.sha256(self.script(data).encode()).hexdigest()}
        self.save(j)
        try:self.remote('stage',j,data=json.dumps({'xyz':v['normalized_xyz'],'script':self.script(data)}).encode())
        except Exception:
            j['state']='staging_failed';self.save(j);raise Unsafe('Staging failed; receipt preserved, no sbatch issued.') from None
        argv=['sbatch','--parsable','--nodes=1','--ntasks=1',f"--cpus-per-task={d['cpus']}",f"--mem={d['memory_mb']}M",f"--time={d['time_minutes']}",'--export=NIL','--job-name='+j['name'],'--chdir='+j['remote_dir'],'--output='+j['remote_dir']+'/scheduler.log','--error='+j['remote_dir']+'/scheduler.log']
        for key in ('partition','account'):
            if d[key]:argv.append('--'+key+'='+d[key])
        argv.append(j['remote_dir']+'/submit.sbatch')
        j['state']='submission_unknown';self.save(j) # Persist before any possible scheduler side effect.
        try:
            reply=self.transport.run(argv).decode().strip()
            if not re.fullmatch('[1-9][0-9]{0,19}',reply):raise Unsafe('Ambiguous scheduler response.')
        except Exception:raise Unsafe('Submission outcome unknown; reconcile receipt by unique job name/workdir, never auto-resubmit.') from None
        j.update(slurm_id=reply,state='submitted');self.save(j);return j
    def query(self,j):
        if not j['slurm_id']:raise Unsafe('No confirmed Slurm ID; manual reconciliation required.')
        raw=self.transport.run(['sacct','--noheader','--parsable2','--allocations','--jobs='+j['slurm_id'],'--format=JobIDRaw,JobName%64,State%40,ExitCode,WorkDir%1024']).decode()
        if len(raw)>65536:raise Unsafe('Scheduler response exceeds limit.')
        lines=[line.split('|') for line in raw.strip().splitlines() if line.strip()]
        if not lines:return None
        if len(lines)!=1:raise Unsafe('Ambiguous scheduler identity.')
        parts=lines[0]
        if len(parts)==6 and parts[-1]=='':parts.pop()
        if len(parts)!=5 or parts[0]!=j['slurm_id'] or parts[1]!=j['name'] or parts[4]!=j['remote_dir']:raise Unsafe('Scheduler identity mismatch; operation refused.')
        state=parts[2].split()[0]
        allowed={'PENDING','RUNNING','SUSPENDED','COMPLETING','COMPLETED','CANCELLED','FAILED','TIMEOUT','OUT_OF_MEMORY','NODE_FAIL','PREEMPTED','BOOT_FAIL','DEADLINE','REQUEUED','REQUEUE_FED','REQUEUE_HOLD','RESIZING','REVOKED','SPECIAL_EXIT'}
        if state not in allowed or not re.fullmatch(r'\d+:\d+',parts[3]):raise Unsafe('Unsupported scheduler response.')
        return {'state':state,'exit_code':parts[3]}
    def status(self,jid):
        self.require();j=self.get(jid);q=self.query(j)
        return {'state':'UNKNOWN','scientific_success':False} if q is None else {**q,'scientific_success':False}
    def cancel(self,jid):
        self.require();j=self.get(jid);q=self.query(j)
        if q is None:raise Unsafe('Cannot verify scheduler identity; cancellation refused.')
        if q['state'] not in ('PENDING','RUNNING','SUSPENDED','COMPLETING','REQUEUED'):return q
        self.transport.run(['scancel','--ctld','--me','--name='+j['name'],j['slurm_id']])
        j['cancel_requested']=True;self.save(j);return {'state':'cancel_requested'}
    def _artifact(self,j,name):
        limits={'output.log':20*1024*1024,'engine.version':8192,'xtbopt.xyz':131072}
        if name not in limits:raise Unsafe('Artifact is not allowlisted.')
        out=self.remote('read',j,name)
        if len(out)>limits[name]:raise Unsafe('Artifact exceeds limit.')
        return out
    def artifact(self,jid,name):
        self.require()
        if name not in ('output.log','engine.version','xtbopt.xyz'):raise Unsafe('Artifact is not allowlisted.')
        j=self.get(jid)
        if self.query(j) is None:raise Unsafe('Cannot verify scheduler identity.')
        return self._artifact(j,name)
    def collect(self,jid):
        self.require();j=self.get(jid);q=self.query(j)
        if q!={'state':'COMPLETED','exit_code':'0:0'}:raise Unsafe('Job has not completed cleanly; no scientific success claimed.')
        version=self._artifact(j,'engine.version').decode(errors='replace')
        match=re.search(r'xtb version\s+(\d+\.\d+\.\d+)',version)
        if not match or match[1]!='6.6.1':raise Unsafe('Unverified remote xTB version; results not accepted.')
        log=self._artifact(j,'output.log').decode(errors='replace')
        xyz=self._artifact(j,'xtbopt.xyz').decode() if j['mode']=='opt' else None
        result=parse_result(log,j['mode'],match[1],xyz,validate_request(j['xyz'],j['charge'],j['uhf'])['atoms'])
        if not result['valid']:result['final_xyz']=None
        directory=self.directory(jid)
        for name,content in [('engine.version',version),('output.log',log),('xtbopt.xyz',xyz)]:
            if content is not None:(directory/name).write_text(content)
        if result['valid']:(directory/'final.xyz').write_text(result['final_xyz'] if j['mode']=='opt' else (directory/'engine.xyz').read_text())
        j.update(version=match[1],state='succeeded' if result['valid'] else 'failed',result=result);self.save(j)
        return j
