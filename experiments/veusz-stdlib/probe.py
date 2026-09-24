"""One-shot Veusz plugin: verify its bundled HTTP standard library, then quit.
Run only in a separate disposable Veusz process, never add to Preferences.
"""
import importlib
import json
import sys
import traceback
from pathlib import Path

# Veusz executes plugins with empty globals, so __file__ is not available.
args = sys.argv
probe_path = Path(args[args.index('--veusz-plugin') + 1]).resolve()
report_path = probe_path.parent / 'results.json'
report = {'executable': sys.executable, 'python': sys.version,
          'frozen': bool(getattr(sys, 'frozen', False)), 'modules': {}}
for name in ('http.server', 'http.client', 'socketserver', 'socket',
             'threading', 'queue', 'json', 'secrets', 'urllib.parse', 'webbrowser'):
    try:
        module = importlib.import_module(name)
        report['modules'][name] = {'ok': True, 'file': getattr(module, '__file__', None)}
    except Exception:
        report['modules'][name] = {'ok': False, 'error': traceback.format_exc()}

try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from http.client import HTTPConnection
    import threading

    class ProbeHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            data = b'veusz-http-ok'
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), ProbeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    try:
        connection.request('GET', '/')
        response = connection.getresponse()
        body = response.read().decode('ascii')
        report['http_test'] = {'status': response.status, 'body': body,
                               'passed': response.status == 200 and body == 'veusz-http-ok'}
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
except Exception:
    report['http_test'] = {'passed': False, 'error': traceback.format_exc()}
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
from veusz import qtall as qt
qt.QTimer.singleShot(0, qt.QApplication.instance().quit)
