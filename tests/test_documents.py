from fastapi.testclient import TestClient
from backend.app import create_app
from test_chemistry import WATER
from test_api import HEAD,wait

DATA={'name':'Water.xyz','xyz':WATER,'charge':0,'uhf':0}

def test_document_persistence_revisions_and_job_snapshot(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        assert c.get('/api/structures').json()==[]
        r=c.post('/api/structures',json=DATA,headers=HEAD)
        assert r.status_code==201,r.text
        doc=r.json();assert doc['revision']==1
        changed={**DATA,'name':'Named water.xyz','revision':1}
        updated=c.post('/api/structures/'+doc['id'],json=changed,headers=HEAD)
        assert updated.status_code==200
        assert updated.json()['revision']==2
        assert c.post('/api/structures/'+doc['id'],json=changed,headers=HEAD).status_code==409
        req={k:DATA[k] for k in ['xyz','charge','uhf']}|{'mode':'sp','structure_id':doc['id'],'structure_revision':2}
        j=c.post('/api/jobs',json=req,headers=HEAD);assert j.status_code==201,j.text
        result=wait(c,j.json()['id'])
        assert result['status']=='succeeded'
        assert result['structure_id']==doc['id'] and result['structure_name']=='Named water.xyz'
        assert c.post('/api/jobs',json={**req,'structure_revision':1},headers=HEAD).status_code==409
        assert c.post('/api/jobs',json={**req,'charge':2},headers=HEAD).status_code==409
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        assert c.get('/api/structures').json()[0]['name']=='Named water.xyz'

def test_document_geometry_validation_and_security(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        for data in [{**DATA,'xyz':'bad'},{**DATA,'name':''},{**DATA,'name':'a\x00b'},{**DATA,'path':'/tmp/arbitrary'}]:
            assert c.post('/api/structures',json=data,headers=HEAD).status_code==422
        assert c.post('/api/structures',json=DATA).status_code==403
        assert c.post('/api/structures',json=DATA,headers={**HEAD,'Origin':'https://evil.example'}).status_code==403
        # Saving a geometry does not require choosing spin yet; run validation still does.
        r=c.post('/api/structures',json={**DATA,'xyz':'1\nH\nH 0 0 0\n'},headers=HEAD)
        assert r.status_code==201
