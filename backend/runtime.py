"""Local platform boundaries: locks and a small engine environment."""
import os
from pathlib import Path

def lock_worker(file):
    try:
        if os.name=='nt':
            import msvcrt
            file.seek(0);file.write(b'0');file.flush();file.seek(0)
            msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        file.close()
        raise RuntimeError('Another workbench already owns this state directory.')

def unlock_worker(file):
    if os.name=='nt':
        import msvcrt
        file.seek(0);msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
    else:
        import fcntl
        fcntl.flock(file,fcntl.LOCK_UN)
    file.close()

def private_config(path):
    p=Path(path)
    return not p.is_symlink() and (os.name=='nt' or (p.stat().st_uid==os.getuid() and not p.stat().st_mode&0o077))

def engine_environment(engine):
    # Retain DLL/Conda search paths and Windows essentials, not user xTB controls.
    env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC'}}
    env.update(PATH=str(Path(engine).parent)+os.pathsep+os.environ.get('PATH',os.defpath),
        HOME=str(Path(engine).parent/'__workbench_no_home__'),LC_ALL='C',
        OMP_NUM_THREADS='1',OMP_STACKSIZE='64M',OPENBLAS_NUM_THREADS='1',
        MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    return env
