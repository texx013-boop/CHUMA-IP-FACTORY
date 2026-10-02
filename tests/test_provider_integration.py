import base64, pathlib, tempfile, threading, json
from http.server import BaseHTTPRequestHandler, HTTPServer
from chuma_ip_factory import CHUMA
from chuma_ip_factory.core import HTTPImageProvider

PNG_1X1 = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n=int(self.headers['Content-Length']); body=self.rfile.read(n); req=json.loads(body)
        payload={'image_base64':base64.b64encode(PNG_1X1).decode(),'mime_type':'image/png','request_echo':req.get('brief',{})}
        raw=json.dumps(payload).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self,*args): pass

class FlakyHandler(Handler):
    attempts=0
    def do_POST(self):
        FlakyHandler.attempts += 1
        if FlakyHandler.attempts < 3:
            self.send_response(503); self.end_headers(); return
        super().do_POST()

def test_http_provider_real_binary_end_to_end():
    server=HTTPServer(('127.0.0.1',0),Handler); threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        provider=HTTPImageProvider(f'http://127.0.0.1:{server.server_port}/generate','test-key')
        d=tempfile.TemporaryDirectory(); c=CHUMA(pathlib.Path(d.name)/'db.sqlite',pathlib.Path(d.name)/'media',image_provider=provider)
        o=c.owner(); cid=c.create_character(o,'HTTP'); cnt=c.create_content(o,cid,{'mechanic':'portrait','hook':'integration'})
        row=c.store.one("SELECT * FROM artifacts WHERE content_id=? AND variant='master'",(cnt,))
        assert row and row['mime_type']=='image/png'
        path=pathlib.Path(row['storage_path']); assert path.exists() and path.read_bytes()==PNG_1X1
        assert c.provider_status()['connected'] is True
        assert c.store.one("SELECT status FROM provider_runs ORDER BY created_at DESC LIMIT 1")['status']=='SUCCEEDED'
        c.store.close(); d.cleanup()
    finally:
        server.shutdown(); server.server_close()

def test_http_provider_retries_transient_5xx():
    FlakyHandler.attempts=0
    server=HTTPServer(('127.0.0.1',0),FlakyHandler); threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        provider=HTTPImageProvider(f'http://127.0.0.1:{server.server_port}/generate','test-key',max_attempts=3,timeout=5,retry_delay=0)
        result=provider.generate({'brief':{'hook':'retry'}})
        assert result['mime_type']=='image/png'
        assert FlakyHandler.attempts==3
    finally:
        server.shutdown(); server.server_close()
