#!/usr/bin/env python3
"""Audit manifest/tracked files only; never read ignored private/runtime content.
Reports categories and filenames, never matched secret values.
"""
from pathlib import Path
import json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
BAD_PARTS={'.private','.runtime','.venv','.tools','state','node_modules','__pycache__','.pytest_cache','evidence','test-results'}
PATTERNS={
 'private-key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'access-token':re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16})'),
 'credential-assignment':re.compile(rb'(?im)^\s*(?:authtoken|access_token|client_secret)\s*[:=]\s*[\"\x27]?[A-Za-z0-9_./+=-]{20,}'),
 'private-home-path':re.compile(rb'(?:/home/[A-Za-z0-9_.-]+/|[A-Z]:\\Users\\[^\\\r\n]+\\)'),
}
def files():
    manifest=ROOT/'SOURCE_MANIFEST.json'
    if manifest.is_file():return [ROOT/p for p in json.loads(manifest.read_text())['files']]+[manifest]
    proc=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True)
    return [ROOT/p.decode() for p in proc.stdout.split(b'\0') if p]
def audit(paths):
    failures=[]
    for p in paths:
        relative=p.relative_to(ROOT)
        if any(part in BAD_PARTS for part in relative.parts) or p.is_symlink() or p.suffix.lower() in ('.log','.db','.sqlite','.sqlite3','.key','.pem','.png','.jpg','.xyz'):
            failures.append((str(relative),'forbidden-file'));continue
        data=p.read_bytes()
        for label,pattern in PATTERNS.items():
            if pattern.search(data):failures.append((str(relative),label))
    if failures:
        print(json.dumps({'passed':False,'findings':failures},indent=2));return 1
    print(json.dumps({'passed':True,'files_checked':len(paths)},indent=2));return 0
if __name__=='__main__':sys.exit(audit(files()))
