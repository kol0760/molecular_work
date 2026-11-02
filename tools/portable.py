#!/usr/bin/env python3
"""Native Windows and Linux launcher; loopback only, no SSH or system changes."""
import argparse,importlib.util,json,os,platform,shutil,socket,subprocess,sys,threading,time,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PORT=int(os.environ.get('WORKBENCH_PORT','8765'))
if not 1024<=PORT<=65535:raise ValueError('Invalid local port; use1024..65535.')
sys.path.insert(0,str(ROOT))
from backend.runtime import private_config

def venv_python():return ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')

def local_engine():
    path=ROOT/'.private/local.json';value=''
    if path.exists():
        if not private_config(path):raise ValueError('Local config must be owned by you, private0600, not a symlink.')
        d=json.loads(path.read_text(encoding='utf-8'))
        if set(d)!={'xtb_executable'} or not isinstance(d['xtb_executable'],str):raise ValueError('Invalid local configuration fields.')
        value=d['xtb_executable']
    value=value or os.environ.get('WORKBENCH_XTB') or shutil.which('xtb')
    if not value:return None
    if not Path(value).is_absolute() or not Path(value).is_file() or not os.access(value,os.X_OK):
        raise ValueError('Set an existing absolute native xTB executable path (xtb.exe on Windows).')
    if os.name=='nt' and Path(value).suffix.lower()!='.exe':raise ValueError('Windows requires a native xtb.exe, not a shell/batch wrapper.')
    return Path(value).resolve()

def validate_environment():
    if platform.system() not in ('Linux','Windows'):raise ValueError('Supported platforms: native Windows and Linux.')
    if sys.version_info<(3,10):raise ValueError('Python3.10+ required.')

def check():
    validate_environment();engine=local_engine()
    return {'platform':platform.system(),'engine_found':bool(engine),'engine_path':str(engine) if engine else None,
        'python_dependencies_present':all(importlib.util.find_spec(n) for n in ('fastapi','uvicorn')),
        'frontend_built':(ROOT/'frontend/dist/index.html').is_file(),'url':f'http://127.0.0.1:{PORT}',
        'slurm':{'connected':False,'message':'Not connected; administrator scaffold only.'}}

def setup():
    validate_environment()
    from init_config import initialize
    initialize()
    folder=ROOT/'.venv';python=venv_python()
    if not folder.exists():subprocess.run([sys.executable,'-m','venv',str(folder)],check=True)
    if not python.is_file():raise ValueError('Existing .venv is incomplete or from another OS; inspect/remove it manually before setup.')
    print('Installing pinned Python packages into project .venv (network required).',flush=True)
    subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.lock.txt')],check=True)
    print('Setup complete. Double-click Start-Windows.cmd on Windows, or run start-linux.sh on Linux.')

def open_when_ready(process,url):
    import urllib.request
    for _ in range(100):
        if process.poll() is not None:return
        try:
            with urllib.request.urlopen(url+'/api/config',timeout=.3) as response:
                if response.status==200:webbrowser.open(url);return
        except OSError:time.sleep(.1)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['check','setup','start'],nargs='?',default='start');args=parser.parse_args()
    if args.action=='check':print(json.dumps(check(),indent=2));return
    if args.action=='setup':setup();return
    validate_environment();engine=local_engine();python=venv_python()
    if not python.is_file():setup()
    if not (ROOT/'frontend/dist/index.html').is_file():raise ValueError('Built frontend absent; see README build instructions.')
    with socket.socket() as s:s.bind(('127.0.0.1',PORT))
    env=dict(os.environ)
    if engine:env['WORKBENCH_XTB']=str(engine)
    url=f'http://127.0.0.1:{PORT}'
    print(f'Local workbench: {url} — Ctrl+C to stop. Keep this window open.',flush=True)
    argv=[str(python),'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',str(PORT),'--workers','1','--no-proxy-headers','--no-access-log']
    if os.name!='nt':os.chdir(ROOT);os.execve(str(python),argv,env)
    from backend.windows_job import own_job
    job_guard=own_job(resource_limits=False) # launcher death also closes the API
    process=subprocess.Popen(argv,cwd=ROOT,env=env,shell=False)
    if os.environ.get('WORKBENCH_NO_BROWSER')!='1':threading.Thread(target=open_when_ready,args=(process,url),daemon=True).start()
    try:result=process.wait()
    except KeyboardInterrupt:
        try:result=process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.terminate();result=process.wait()
    raise SystemExit(result)

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,subprocess.SubprocessError,OSError) as e:
        print('Cannot start: '+str(e),file=sys.stderr);sys.exit(1)
