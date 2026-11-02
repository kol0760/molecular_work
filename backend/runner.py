"""Linux child bootstrap: bounded resources and death with the owning API process."""
import ctypes
import os
import resource
import signal
import sys

parent=int(sys.argv[1])
libc=ctypes.CDLL(None,use_errno=True)
if libc.prctl(1,signal.SIGKILL,0,0,0)!=0:
    raise RuntimeError('Cannot protect engine process lifetime')
if os.getppid()!=parent:
    sys.exit(125)
resource.setrlimit(resource.RLIMIT_CPU,(600,605))
resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024*1024,20*1024*1024))
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
os.nice(10)
os.execve(sys.argv[2],sys.argv[2:],dict(os.environ))
