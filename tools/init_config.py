#!/usr/bin/env python3
"""Create blank private examples only; never overwrite settings or generate keys."""
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[1]
def initialize():
    directory=ROOT/'.private';directory.mkdir(mode=0o700,exist_ok=True)
    if directory.is_symlink() or directory.stat().st_mode&0o077:raise ValueError('Private directory must be a real private0700 directory.')
    for name in ('local','slurm'):
        path=directory/(name+'.json')
        try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:continue
        with os.fdopen(fd,'w') as f:f.write((ROOT/'config'/(name+'.example.json')).read_text())
if __name__=='__main__':initialize();print('Blank private config initialized; existing settings unchanged.')
