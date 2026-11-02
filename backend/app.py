from contextlib import asynccontextmanager
from pathlib import Path
import json
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .chemistry import validate_request, ELEMENTS
from .jobs import JobStore,LIMITS
from .security import allowed_request
from .documents import Documents,Conflict

BASE=Path(__file__).resolve().parents[1]

def create_app(state_dir=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.jobs=JobStore(state_dir or BASE/'state');app.state.documents=Documents(state_dir or BASE/'state');app.state.jobs.start()
        try:yield
        finally:app.state.documents.close();app.state.jobs.close()
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    @app.middleware('http')
    async def protect(request,call_next):
        host=request.headers.get('host','')
        if not allowed_request(host,None):
            return JSONResponse({'detail':'Invalid local Host.'},400)
        origin=request.headers.get('origin')
        if not allowed_request(host,origin):return JSONResponse({'detail':'Cross-origin requests are forbidden.'},403)
        # External links may enter the application shell. Never extend this
        # exception to API reads, artifacts, embedded documents or mutations.
        shell_navigation=(request.method in ('GET','HEAD') and request.url.path=='/'
            and request.headers.get('sec-fetch-mode')=='navigate'
            and request.headers.get('sec-fetch-dest')=='document')
        if request.headers.get('sec-fetch-site') in ('cross-site','same-site') and not shell_navigation:
            return JSONResponse({'detail':'Only same-origin access is allowed.'},403)
        if request.method not in ('GET','HEAD'):
            if request.headers.get('x-workbench')!='1' or request.headers.get('content-type','').split(';')[0]!='application/json':
                return JSONResponse({'detail':'Application JSON and X-Workbench header required.'},403)
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>139264:return JSONResponse({'detail':'Request exceeds size limit.'},413)
            request._body=bytes(body)
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
        return response
    def store():return app.state.jobs
    def get(jid):
        try:return store().get(jid)
        except KeyError:raise HTTPException(404,'Job not found.')
    async def payload(request):
        try:
            d=await request.json()
            required={'xyz','charge','uhf','mode'}
            if not isinstance(d,dict) or not required.issubset(d) or set(d)-required-{'structure_id','structure_revision'}:raise ValueError('Provide xyz, charge, uhf and mode; only optional structure_id/revision associations are supported.')
            if ('structure_id' in d)!=('structure_revision' in d):raise ValueError('Structure ID and revision must be supplied together.')
            if d['mode'] not in ('sp','opt'):raise ValueError('Mode must be sp or opt.')
            validated=validate_request(d['xyz'],d['charge'],d['uhf'])
            return d,validated
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(422,str(e))
    @app.get('/api/config')
    def config():return {'version':store().version,'engine_error':store().engine_error,'engine_warning':store().engine_warning,'backend':'local','backends':[{'id':'local','available':store().engine_error is None},{'id':'slurm','available':False}],'platform':os.name,'limits':LIMITS,'elements':ELEMENTS,'method':'GFN2-xTB','phase':'gas'}
    @app.post('/api/validate')
    async def validate(request:Request):
        _,v=await payload(request);return v
    @app.get('/api/structures')
    def structures():return app.state.documents.list()
    async def save_structure(request,identity=None):
        try:return app.state.documents.save(await request.json(),identity)
        except Conflict as e:raise HTTPException(409,str(e))
        except KeyError:raise HTTPException(404,'Structure not found.')
        except (ValueError,TypeError) as e:raise HTTPException(422,str(e))
    @app.post('/api/structures',status_code=201)
    async def create_structure(request:Request):return await save_structure(request)
    @app.post('/api/structures/{identity}')
    async def update_structure(identity:str,request:Request):return await save_structure(request,identity)
    @app.get('/api/jobs')
    def jobs():return [{k:v for k,v in j.items() if k not in ('xyz','result')}|{'result':{k:v for k,v in (j['result'] or {}).items() if k!='final_xyz'}} for j in store().list()]
    @app.post('/api/jobs',status_code=201)
    async def submit(request:Request):
        d,_=await payload(request)
        if 'structure_id' in d:
            try:doc=app.state.documents.get(d['structure_id'])
            except (KeyError,TypeError):raise HTTPException(404,'Structure not found.')
            if type(d['structure_revision']) is not int or doc['revision']!=d['structure_revision'] or any(doc[k]!=d[k] for k in ['xyz','charge','uhf']):raise HTTPException(409,'Save the current structure before running; its revision/settings changed.')
            d['structure_name']=doc['name']
        try:jid=store().submit(d)
        except ValueError as e:raise HTTPException(422,str(e))
        return {'id':jid}
    @app.get('/api/jobs/{jid}')
    def job(jid:str):
        j=get(jid)
        p=store().directory(jid)/'output.log'
        # Bounded tail for live display; download retains the complete bounded file.
        with p.open('rb') as f:
            size=p.stat().st_size;f.seek(max(0,size-200000));text=f.read(200000).decode(errors='replace')
        return {**j,'log':text,'log_truncated':size>200000}
    @app.post('/api/jobs/{jid}/cancel')
    def cancel(jid:str):
        get(jid);return store().cancel(jid)
    @app.get('/api/jobs/{jid}/files/{artifact}')
    def artifact(jid:str,artifact:str):
        j=get(jid)
        if artifact not in ('input.xyz','engine.xyz','final.xyz','output.log','provenance.json'):raise HTTPException(404,'Artifact not found.')
        if artifact=='final.xyz' and j['status']!='succeeded':raise HTTPException(404,'No validated final geometry.')
        path=store().directory(jid)/artifact
        if not path.is_file():raise HTTPException(404,'Artifact not found.')
        return FileResponse(path,filename=f'{jid[:8]}-{artifact}',media_type='application/json' if artifact.endswith('.json') else 'text/plain')
    dist=BASE/'frontend/dist'
    if dist.is_dir():app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
    return app

app=create_app()
