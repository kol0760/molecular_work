"""CI only: fetch pinned upstream xTB into a supplied temporary directory.

Never redistribute or silently install a calculator for desktop users.
"""
import hashlib
import os
from pathlib import Path
import sys
import tarfile
import urllib.request
import zipfile

WINDOWS=('xtb-6.7.1pre-windows-x86_64.zip','043e578da4a7e114a4d584972959a875e3ffb9f2767a86723b95aa6719d28d9c')
LINUX=('xtb-6.7.1-linux-x86_64.tar.xz','62a8d18778286e815292ee53d76ce447daf460a4dea3782c0f25cbac7019b5df')

def install(target):
    target=Path(target).resolve();target.mkdir(parents=True,exist_ok=True)
    name,digest=WINDOWS if os.name=='nt' else LINUX
    archive=target/name
    urllib.request.urlretrieve('https://github.com/grimme-lab/xtb/releases/download/v6.7.1/'+name,archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=digest:raise ValueError('Upstream checksum mismatch')
    if os.name=='nt':
        with zipfile.ZipFile(archive) as z:z.extractall(target)
    else:
        with tarfile.open(archive) as t:t.extractall(target)
    engines=list(target.rglob('xtb.exe' if os.name=='nt' else 'xtb'))
    engine=next(p for p in engines if p.is_file())
    # DLLs shipped alongside the official Windows binary remain adjacent.
    with open(os.environ['GITHUB_ENV'],'a',encoding='utf-8') as f:f.write('WORKBENCH_XTB='+str(engine)+'\n')
    print('Verified upstream xTB:',name)
if __name__=='__main__':install(sys.argv[1])
