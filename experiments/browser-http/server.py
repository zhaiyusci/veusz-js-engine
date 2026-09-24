"""Isolated browser-as-JS-engine experiment; Python standard library only."""
import argparse
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import webbrowser
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FEATURE = ROOT / 'features' / 'mathjax'


class Bridge:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.tasks = queue.Queue()
        self.pending = {}
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.client = None
        self.user_agent = None
        self.fatal_error = None

    def fail(self, message):
        with self.lock:
            self.fatal_error = str(message)[:4000]
            self.ready.set()
            for target in self.pending.values():
                if not target.full():
                    target.put_nowait({'error': self.fatal_error})

    def accept_client(self, client, user_agent):
        with self.lock:
            if self.client not in (None, client):
                return False
            self.client = client
            self.user_agent = user_agent
            self.ready.set()
            return True

    def rpc(self, op, timeout=30, **params):
        ident = secrets.token_hex(12)
        answer = queue.Queue(maxsize=1)
        with self.lock:
            if self.fatal_error:
                raise RuntimeError(self.fatal_error)
            self.pending[ident] = answer
        self.tasks.put(dict(id=ident, op=op, **params))
        try:
            reply = answer.get(timeout=timeout)
            if 'error' in reply:
                raise RuntimeError(reply['error'])
            return reply['value'], reply.get('elapsed_ms')
        except queue.Empty:
            raise TimeoutError(f'Browser did not answer {op} within {timeout}s') from None
        finally:
            with self.lock:
                self.pending.pop(ident, None)

    def deliver(self, reply):
        with self.lock:
            target = self.pending.get(reply.get('id'))
            if target is None or target.full():
                return False
            target.put_nowait(reply)
            return True


def make_server(bridge):
    assets = {'jsapi.js': ROOT / 'jsapi.js', 'feature.js': FEATURE / 'feature.js',
              'mathjax.js': FEATURE / 'mathjax.js'}
    assets.update({'fonts/' + p.name: p for p in (FEATURE / 'fonts').glob('*.js')})
    heads = []
    for name, path in assets.items():
        if name != 'jsapi.js':
            with path.open(encoding='utf-8-sig') as source:
                heads.append({'file': name, 'head': source.read(16384)})

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, mime='application/json'):
            body = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; img-src 'self' blob:; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def permitted(self, auth=True):
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected:
                self.send(403, {'error': 'host'})
                return False
            origin = self.headers.get('Origin')
            if origin is not None and origin != 'http://' + expected:
                self.send(403, {'error': 'origin'})
                return False
            query = parse_qs(urlsplit(self.path).query)
            token = self.headers.get('X-Session-Token') or query.get('token', [''])[0]
            if auth and not secrets.compare_digest(token, bridge.token):
                self.send(403, {'error': 'token'})
                return False
            return True

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self.permitted(auth=path not in ('/', '/page.js')):
                return
            if path in ('/', '/page.js', '/worker.js'):
                name = {'/': 'index.html', '/page.js': 'page.js', '/worker.js': 'worker.js'}[path]
                mime = 'text/html; charset=utf-8' if path == '/' else 'text/javascript; charset=utf-8'
                self.send(200, (HERE / name).read_bytes(), mime)
            elif path == '/heads':
                self.send(200, heads)
            elif path.startswith('/assets/') and path[8:] in assets:
                self.send(200, assets[path[8:]].read_bytes(), 'text/javascript; charset=utf-8')
            elif path == '/task':
                if self.headers.get('X-Client-Id') != bridge.client:
                    self.send(409, {'error': 'client'})
                    return
                try:
                    task = bridge.tasks.get(timeout=10)
                except queue.Empty:
                    task = None
                self.send(200, task)
            else:
                self.send(404, {'error': 'not found'})

        def do_POST(self):
            if not self.permitted():
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16 * 1024 * 1024:
                    raise ValueError('body size')
                self.connection.settimeout(10)
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('object expected')
            except (ValueError, OSError):
                self.send(400, {'error': 'invalid body'})
                return
            path = urlsplit(self.path).path
            if path == '/fatal':
                # Authenticated page errors may arrive before the Worker is ready.
                bridge.fail(body.get('error', 'Browser failed'))
                self.send(200, {'ok': True})
            elif path == '/ready':
                client = body.get('client')
                if not isinstance(client, str) or not 1 <= len(client) <= 128:
                    self.send(400, {'error': 'client'})
                elif bridge.accept_client(client, body.get('userAgent')):
                    self.send(200, {'ok': True})
                else:
                    self.send(409, {'error': 'another browser already owns this session'})
            elif path == '/reply':
                if self.headers.get('X-Client-Id') != bridge.client:
                    self.send(409, {'error': 'client'})
                elif not isinstance(body.get('id'), str) or not ('value' in body or 'error' in body):
                    self.send(400, {'error': 'invalid reply'})
                else:
                    self.send(200 if bridge.deliver(body) else 409, {'ok': True})
            else:
                self.send(404, {'error': 'not found'})

    return ThreadingHTTPServer(('127.0.0.1', 0), Handler)


def run_suite(bridge, output):
    if not bridge.ready.wait(60):
        raise TimeoutError('No browser connected within 60 seconds')
    results = {'user_agent': bridge.user_agent, 'cases': [], 'scope': 'HTTP browser prototype; no Qt text measurement or Veusz integration'}
    description, _ = bridge.rpc('call', name='veuszDescribe', payload='')
    spec = json.loads(description)
    assert spec['name'] == 'mathjax', spec
    fonts = next(p for p in spec['properties'] if p['name'] == 'font')
    default_font = fonts['default']
    # This repository ships Asana as external font data, not in mathjax.js.
    lazy = next((f for f in fonts['choices'] if f['value'] == 'asana'), None)
    if lazy is None:
        raise RuntimeError('Asana font declaration missing; cannot test deferred font loading')
    loaded = set()

    def render(label, tex, font=default_font):
        request = {'text': tex, 'size': 20, 'color': '#000000', 'props': {'on': True, 'display': True, 'font': font}}
        loads = []
        elapsed_js = 0
        start = time.perf_counter()
        for _ in range(32):
            raw, elapsed = bridge.rpc('call', name='veuszRender', payload=json.dumps(request))
            elapsed_js += elapsed or 0
            reply = json.loads(raw)
            if 'load' in reply:
                file = reply['load']
                if file in loaded:
                    raise RuntimeError('Repeated load: ' + file)
                bridge.rpc('load', file=file)
                loaded.add(file)
                loads.append(file)
                continue
            if 'measure' in reply:
                raise RuntimeError('Qt text measurement intentionally not implemented in this prototype')
            if 'svg' not in reply or reply.get('error'):
                raise RuntimeError(str(reply)[:500])
            svg = reply['svg']
            tree = ET.fromstring(svg)
            assert tree.tag.endswith('svg') and any(e.tag.endswith('path') for e in tree.iter())
            (output / (label + '.svg')).write_text(svg, encoding='utf-8')
            results['cases'].append({'name': label, 'font': font, 'round_trip_ms': round((time.perf_counter()-start)*1000, 3), 'js_call_ms': round(elapsed_js, 3), 'loads': loads, 'svg_bytes': len(svg.encode()), 'width': reply.get('width'), 'height': reply.get('height')})
            return svg
        raise RuntimeError('Excessive render passes')

    first = render('fraction', r'\frac{a^2+b^2}{c^2}')
    render('integral', r'\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}')
    again = render('fraction-repeat', r'\frac{a^2+b^2}{c^2}')
    assert first == again, 'Repeated render changed output'
    results['repeat_exact_match'] = True
    render('alternate-font', r'\sum_{n=1}^{\infty}\frac{1}{n^2}=\frac{\pi^2}{6}', lazy['value'])
    assert any(name.startswith('fonts/') for name in results['cases'][-1]['loads']), 'External font was not loaded'
    results['status'] = 'passed'
    (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=True, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true', help='Open the default browser')
    parser.add_argument('--browser', help='Launch this browser executable with an isolated profile')
    parser.add_argument('--headless', action='store_true', help='Use with --browser for automated real-browser testing')
    parser.add_argument('--once', action='store_true', help='Exit after the test suite')
    parser.add_argument('--output-dir', type=Path, default=HERE / 'output', help='Separate result directory for browser comparisons')
    args = parser.parse_args()
    if args.headless and not args.browser:
        parser.error('--headless requires --browser')
    bridge = Bridge()
    server = make_server(bridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_text(json.dumps({'status': 'running'}), encoding='utf-8')
    url = f'http://127.0.0.1:{server.server_port}/#token={bridge.token}'
    print('Open this private session URL: ' + url, flush=True)
    browser = None
    log = None
    try:
        if args.browser:
            profile = output / ('profile-' + secrets.token_hex(6))
            log = (output / 'browser.log').open('wb')
            if Path(args.browser).stem.lower() == 'firefox':
                profile.mkdir()
                command = [args.browser, '-no-remote', '-profile', str(profile)]
                if args.headless:
                    command.append('-headless')
            else:
                command = [args.browser, '--user-data-dir=' + str(profile), '--no-first-run', '--no-default-browser-check', '--disable-background-networking']
                if args.headless:
                    command.append('--headless=new')
            browser = subprocess.Popen(command + [url], stdout=log, stderr=log)
        elif args.open:
            webbrowser.open(url)
        run_suite(bridge, output)
        if not args.once:
            print('Suite passed. Server remains available; Ctrl+C to stop. Reload/reconnect requires a server restart.', flush=True)
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        (output / 'results.json').write_text(json.dumps({'status': 'failed', 'error': str(error)}, indent=2), encoding='utf-8')
        raise
    finally:
        server.shutdown()
        server.server_close()
        if browser is not None and browser.poll() is None:
            # Only the independently launched profile/process tree is terminated.
            subprocess.run(['taskkill', '/PID', str(browser.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            browser.wait(timeout=10)
        if log:
            log.close()


if __name__ == '__main__':
    main()
