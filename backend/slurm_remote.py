"""Fixed remote Python helper, transported as code; never a public API input."""
REMOTE = r'''
import hashlib,json,os,stat,sys
op,root,jid,sha=sys.argv[1:5]
flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
fd=os.open('/',flags)
for part in root.strip('/').split('/'):
    new=os.open(part,flags,dir_fd=fd);os.close(fd);fd=new
s=os.fstat(fd)
if s.st_uid!=os.getuid() or s.st_mode&0o077:raise RuntimeError('root must be private and owned')
if op=='stage':os.mkdir(jid,0o700,dir_fd=fd)
new=os.open(jid,flags,dir_fd=fd);os.close(fd);fd=new
s=os.fstat(fd)
if s.st_uid!=os.getuid() or s.st_mode&0o077:raise RuntimeError('unsafe job directory')
def read(name,limit):
    f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    try:
        st=os.fstat(f)
        if not stat.S_ISREG(st.st_mode) or st.st_size>limit:raise RuntimeError('unsafe artifact')
        chunks=[];total=0
        while True:
            data=os.read(f,min(65536,limit+1-total))
            if not data:break
            chunks.append(data);total+=len(data)
            if total>limit:raise RuntimeError('artifact too large')
        return b''.join(chunks)
    finally:os.close(f)
if op=='stage':
    p=json.loads(sys.stdin.buffer.read(262145))
    if hashlib.sha256(p['xyz'].encode()).hexdigest()!=sha:raise RuntimeError('input mismatch')
    for name,data in [('engine.xyz',p['xyz']),('submit.sbatch',p['script']),('.identity',json.dumps({'id':jid,'sha':sha}))]:
        f=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(f,'wb') as out:out.write(data.encode())
elif op=='read':
    if json.loads(read('.identity',1024))!={'id':jid,'sha':sha}:raise RuntimeError('identity mismatch')
    if hashlib.sha256(read('engine.xyz',131072)).hexdigest()!=sha:raise RuntimeError('input changed')
    name=sys.argv[5]
    if name not in ('output.log','engine.version','xtbopt.xyz'):raise RuntimeError('invalid artifact')
    limit=20971520 if name=='output.log' else (131072 if name=='xtbopt.xyz' else 8192)
    sys.stdout.buffer.write(read(name,limit))
else:raise RuntimeError('invalid operation')
os.close(fd)
'''
