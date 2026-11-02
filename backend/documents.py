"""Named geometries are independent from immutable calculation snapshots."""
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from .chemistry import parse_xyz

class Conflict(ValueError):pass

class Documents:
    def __init__(self,root):
        self.db=sqlite3.connect(Path(root)/'structures.sqlite',check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS structures (id TEXT PRIMARY KEY, data TEXT NOT NULL)');self.db.commit()
        self.lock=threading.RLock()
    def get(self,identity):
        if not re.fullmatch(r'[0-9a-f]{32}',identity):raise KeyError(identity)
        with self.lock:row=self.db.execute('SELECT data FROM structures WHERE id=?',(identity,)).fetchone()
        if not row:raise KeyError(identity)
        return json.loads(row[0])
    def list(self):
        with self.lock:rows=self.db.execute('SELECT data FROM structures ORDER BY rowid').fetchall()
        return [json.loads(r[0]) for r in rows]
    def save(self,data,identity=None):
        required={'name','xyz','charge','uhf'}|({'revision'} if identity else set())
        if not isinstance(data,dict) or set(data)!=required:raise ValueError('Provide name, xyz, charge, uhf and the existing revision for updates.')
        name=data['name']
        if not isinstance(name,str) or not name.strip() or len(name)>120 or any(ord(c)<32 for c in name):raise ValueError('Structure name must contain 1–120 printable characters.')
        parse_xyz(data['xyz'])
        if type(data['charge']) is not int or not -20<=data['charge']<=20 or type(data['uhf']) is not int or not 0<=data['uhf']<=20:raise ValueError('Charge and unpaired electrons must be integers within supported limits.')
        with self.lock:
            old=self.get(identity) if identity else None
            if old and (type(data['revision']) is not int or data['revision']!=old['revision']):raise Conflict('Structure changed in another window. Reopen it before saving; your local draft is retained.')
            if not old and len(self.list())>=100:raise ValueError('At most 100 saved structures are supported.')
            doc={k:data[k] for k in ['name','xyz','charge','uhf']}
            doc.update(name=name.strip(),id=identity or uuid.uuid4().hex,revision=old['revision']+1 if old else 1,created=old['created'] if old else time.time(),updated=time.time())
            self.db.execute('INSERT INTO structures VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(doc['id'],json.dumps(doc)));self.db.commit()
            return doc
    def close(self):self.db.close()
