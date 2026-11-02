from backend.security import allowed_request

def test_loopback_only():
    assert allowed_request('127.0.0.1:8765',None)
    assert allowed_request('localhost:8765','http://localhost:8765')
    assert not allowed_request('public.example',None)
    assert not allowed_request('localhost:8765','https://evil.example')
    assert not allowed_request('localhost:8765','http://127.0.0.1:8765')
