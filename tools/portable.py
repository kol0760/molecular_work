#!/usr/bin/env python3
"""Local Linux/WSL2 launcher. Does not configure network access or SSH."""
import argparse,importlib.util,json,os,platform,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PORT=int(os.environ.get('WORKBENCH_PORT','8765'))
if not 1024<=PORT<=65535:raise ValueError('Invalid local port; use1024..65535.')
sys.path.insert(0,str(ROOT))
def local_engine():
    path=ROOT/'.private/local.json';value=''
    if path.exists():
        if path.is_symlink() or path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o077:raise ValueError('Local config must be owned by you, private0600, not a symlink.')
        d=json.loads(path.read_text())
        if set(d)!={'xtb_executable'} or not isinstance(d['xtb_executable'],str):raise ValueError('Invalid local configuration fields.')
        value=d['xtb_executable']
    value=value or os.environ.get('WORKBENCH_XTB') or shutil.which('xtb')
    if not value or not Path(value).is_absolute() or not Path(value).is_file() or not os.access(value,os.X_OK):raise ValueError('Install xTB6.6.1 inside Linux/WSL2, or set absolute xtb_executable in private local.json.')
    p=Path(value).resolve()
    proc=subprocess.run([str(p),'--version'],capture_output=True,text=True,timeout=10,shell=False,env={'PATH':str(p.parent)+':/usr/bin:/bin','HOME':'/nonexistent','LC_ALL':'C'})
    match=re.search(r'xtb version\s+(\d+\.\d+\.\d+)',proc.stdout+proc.stderr)
    if proc.returncode or not match or match[1]!='6.6.1':raise ValueError('This scientific parser requires actual xTB6.6.1.')
    return p

def validate_environment():
    if platform.system()!='Linux':raise ValueError('Native Windows is unsupported. Use Start-Windows.cmd with WSL2 or start-linux.sh inside Linux.')
    if sys.version_info<(3,10):raise ValueError('Python3.10+ required.')

def check():
    validate_environment();engine=local_engine()
    from backend.slurm import Config,SlurmAdapter
    slurm=SlurmAdapter(Config.load(ROOT/'.private/slurm.json'),ROOT/'.private/slurm-receipts').connection()
    dependencies=all(importlib.util.find_spec(name) for name in ('fastapi','uvicorn'))
    return {'platform':'Linux/WSL-compatible','xtb_version':'6.6.1','engine_found':bool(engine),'python_dependencies_present':dependencies,'frontend_built':(ROOT/'frontend/dist/index.html').is_file(),'url':f'http://127.0.0.1:{PORT}','slurm':slurm}

def setup():
    validate_environment()
    from init_config import initialize
    initialize();local_engine()
    folder=ROOT/'.venv';python=folder/'bin/python'
    if not folder.exists():subprocess.run([sys.executable,'-m','venv',str(folder)],check=True)
    if not python.is_file():raise ValueError('Existing .venv is incomplete; inspect/remove it manually before setup.')
    print('Installing pinned Python packages into project .venv (network required).',flush=True)
    subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.lock.txt')],check=True)
    print('Setup complete. Run start-linux.sh, then open http://127.0.0.1:8765.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['check','setup','start'],nargs='?',default='start');args=parser.parse_args()
    if args.action=='check':print(json.dumps(check(),indent=2));return
    if args.action=='setup':setup();return
    validate_environment();engine=local_engine();python=ROOT/'.venv/bin/python'
    if not python.is_file():setup()
    if not (ROOT/'frontend/dist/index.html').is_file():raise ValueError('Built frontend absent; see README build instructions.')
    os.chdir(ROOT);env=dict(os.environ);env['WORKBENCH_XTB']=str(engine)
    print(f'Local workbench: http://127.0.0.1:{PORT} — Ctrl+C to stop. No public listener.',flush=True)
    os.execve(str(python),[str(python),'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',str(PORT),'--workers','1','--no-proxy-headers','--no-access-log'],env)
if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,subprocess.SubprocessError,OSError) as e:
        print('Cannot start: '+str(e),file=sys.stderr);sys.exit(1)
