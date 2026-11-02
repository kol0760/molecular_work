"""Own a kill-on-close Job Object before spawning the Windows engine.

No process-name matching, taskkill or global enumeration. Fail closed if
containment cannot be established, before executing the engine.
"""
import ctypes as C
from ctypes import wintypes as W
import subprocess
import threading

class BasicLimits(C.Structure):
    _fields_=[('process_time',C.c_int64),('job_time',C.c_int64),('flags',W.DWORD),
        ('min_working_set',C.c_size_t),('max_working_set',C.c_size_t),('active_processes',W.DWORD),
        ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]

class IOCounters(C.Structure):
    _fields_=[(name,C.c_uint64) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]

class ExtendedLimits(C.Structure):
    _fields_=[('basic',BasicLimits),('io',IOCounters),('process_memory',C.c_size_t),
        ('job_memory',C.c_size_t),('peak_process_memory',C.c_size_t),('peak_job_memory',C.c_size_t)]

def own_job(resource_limits=True):
    kernel=C.WinDLL('kernel32',use_last_error=True)
    signatures={
        'CreateJobObjectW':([C.c_void_p,W.LPCWSTR],W.HANDLE),
        'SetInformationJobObject':([W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL),
        'AssignProcessToJobObject':([W.HANDLE,W.HANDLE],W.BOOL),
        'GetCurrentProcess':([],W.HANDLE),
        'OpenProcess':([W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
        'WaitForSingleObject':([W.HANDLE,W.DWORD],W.DWORD),
        'TerminateJobObject':([W.HANDLE,W.UINT],W.BOOL),
        'CloseHandle':([W.HANDLE],W.BOOL),
    }
    for name,(args,result) in signatures.items():
        fn=getattr(kernel,name);fn.argtypes=args;fn.restype=result
    def require(value):
        if not value:raise C.WinError(C.get_last_error())
        return value
    job=require(kernel.CreateJobObjectW(None,None))
    limits=ExtendedLimits()
    limits.basic.flags=0x2000 # kill on close
    if resource_limits:
        limits.basic.flags|=0x200|0x4 # aggregate memory and job CPU time
        limits.basic.job_time=600*10_000_000
        limits.job_memory=2*1024**3
    require(kernel.SetInformationJobObject(job,9,C.byref(limits),C.sizeof(limits)))
    require(kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()))
    return kernel,job

def run(parent,argv):
    kernel,job=own_job()
    owner=kernel.OpenProcess(0x100000,False,parent) # SYNCHRONIZE only
    if not owner:raise C.WinError(C.get_last_error())
    if kernel.WaitForSingleObject(owner,0)!=0x102:return 125
    def watch():
        kernel.WaitForSingleObject(owner,0xFFFFFFFF)
        kernel.TerminateJobObject(job,125)
    threading.Thread(target=watch,daemon=True).start()
    # Child inherits membership, never the non-inheritable job handle.
    child=subprocess.Popen(argv,shell=False,creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    result=child.wait()
    kernel.CloseHandle(owner)
    # Process exit closes job and terminates remaining descendants.
    return result
