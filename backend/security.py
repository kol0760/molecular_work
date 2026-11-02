"""Loopback-only authorities. Port is local administrator configuration."""
import os
PORT=int(os.environ.get('WORKBENCH_PORT','8765'))
if not 1024<=PORT<=65535:raise ValueError('Invalid local port; use1024..65535.')
LOCAL_HOSTS={f'127.0.0.1:{PORT}',f'localhost:{PORT}','127.0.0.1','localhost'}
def allowed_request(host,origin):
    return host in LOCAL_HOSTS and (origin is None or origin==f'http://{host}')
