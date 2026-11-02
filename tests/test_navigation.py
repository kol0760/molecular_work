"""External links may open the shell; they may not read APIs or change state."""
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app

NAV={'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document','Sec-Fetch-User':'?1','Referer':'https://chatgpt.com/'}

@pytest.mark.parametrize('site',['cross-site','same-site'])
@pytest.mark.parametrize('method',['GET','HEAD'])
def test_external_top_level_link_opens_shell(tmp_path,site,method):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        r=c.request(method,'/',headers={**NAV,'Sec-Fetch-Site':site})
        assert r.status_code==200
        assert r.headers['content-type'].startswith('text/html')
        assert r.headers['x-frame-options']=='DENY'

@pytest.mark.parametrize('path,method,extra',[
    ('/api/config','GET',{}),('/api/jobs','GET',{}),('/api/structures','GET',{}),
    ('/api/jobs/unknown/files/input.xyz','GET',{}),
    ('/api/jobs','POST',{'X-Workbench':'1','Content-Type':'application/json'}),
    ('/','POST',{'X-Workbench':'1','Content-Type':'application/json'}),
    ('/','GET',{'Sec-Fetch-Dest':'iframe'}),
    ('/','GET',{'Sec-Fetch-Dest':'empty','Sec-Fetch-Mode':'cors'}),
    ('/','GET',{'Origin':'https://evil.example'}),
    ('/','GET',{'Host':'evil.example'}),
])
def test_external_navigation_never_bypasses_security(tmp_path,path,method,extra):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        r=c.request(method,path,headers={**NAV,**extra})
        assert r.status_code in (400,403)

def test_direct_and_same_origin_access_still_work(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8765') as c:
        assert c.get('/').status_code==200
        assert c.get('/api/config',headers={'Sec-Fetch-Site':'same-origin'}).status_code==200
