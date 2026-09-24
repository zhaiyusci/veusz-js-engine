"""Disposable Veusz-hosted HTTP/browser experiment. DO NOT install in Preferences.
Launch with veusz.exe --veusz-plugin <absolute path to this file>.
"""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import traceback

from veusz import qtall as qt

PLUGIN = Path(sys.argv[sys.argv.index('--veusz-plugin') + 1]).resolve()
HERE = PLUGIN.parent
OUTPUT = HERE / 'output'
OUTPUT.mkdir(exist_ok=True)
REPORT_PATH = OUTPUT / 'results.json'
REPORT = {
    'status': 'running',
    'host': {'executable': sys.executable, 'python': sys.version,
             'frozen': bool(getattr(sys, 'frozen', False)), 'pid': os.getpid()},
    'scope': 'HTTP and RPC hosted inside Veusz; browser MathJax; Qt SVG rasterization. Not connected to document drawing or text measurement.',
}
DONE = threading.Event()


def save_report():
    REPORT_PATH.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')


save_report()


def work():
    server = None
    serving = None
    browser = None
    browser_log = None
    try:
        spec = importlib.util.spec_from_file_location(
            'veusz_http_experiment', HERE.parent / 'browser-http' / 'server.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import http.server
        REPORT['host']['http_server_module'] = http.server.__file__
        bridge = module.Bridge()
        server = module.make_server(bridge)
        REPORT['http'] = {'host': '127.0.0.1', 'port': server.server_port,
                          'owner_pid': os.getpid()}
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        url = f'http://127.0.0.1:{server.server_port}/#token={bridge.token}'
        executable = Path(os.environ.get('VEUSZ_HTTP_TEST_BROWSER', r'C:\Program Files\Mozilla Firefox\firefox.exe'))
        if not executable.is_file():
            raise FileNotFoundError(executable)
        profile = OUTPUT / ('profile-' + secrets.token_hex(6))
        if executable.stem.lower() == 'firefox':
            profile.mkdir()
            command = [str(executable), '-no-remote', '-profile', str(profile), '-headless', url]
        else:
            command = [str(executable), '--user-data-dir=' + str(profile), '--headless=new',
                       '--no-first-run', '--no-default-browser-check', '--disable-background-networking', url]
        browser_log = (OUTPUT / 'browser.log').open('wb')
        browser = subprocess.Popen(command, stdout=browser_log, stderr=browser_log)
        REPORT['browser'] = {'executable': str(executable), 'pid': browser.pid, 'isolated_profile': str(profile)}
        save_report()
        suite_output = OUTPUT / 'suite'
        suite_output.mkdir(exist_ok=True)
        (suite_output / 'results.json').write_text('{"status":"running"}', encoding='utf-8')
        # Windowed/frozen Veusz may have sys.stdout=None.
        with (OUTPUT / 'suite.log').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
            module.run_suite(bridge, suite_output)
        REPORT['suite'] = json.loads((suite_output / 'results.json').read_text(encoding='utf-8'))
        # The reused suite's original scope describes its standalone launcher.
        REPORT['suite']['scope'] = REPORT['scope']
        baseline = HERE.parent / 'browser-http' / 'output' / 'firefox'
        REPORT['baseline_byte_matches'] = {
            svg.name: svg.read_bytes() == (baseline / svg.name).read_bytes()
            for svg in suite_output.glob('*.svg') if (baseline / svg.name).is_file()
        }
        if not all(REPORT['baseline_byte_matches'].values()):
            raise RuntimeError('Output differs from the saved standalone Firefox baseline')
        REPORT['status'] = 'awaiting_qt_validation'
    except Exception:
        REPORT['status'] = 'failed'
        REPORT['error'] = traceback.format_exc()
    finally:
        try:
            if server is not None:
                if serving is not None:
                    server.shutdown()
                    serving.join(timeout=5)
                server.server_close()
                REPORT['http_closed'] = True
            if browser is not None:
                if browser.poll() is None:
                    with (OUTPUT / 'cleanup.log').open('wb') as log:
                        completed = subprocess.run(['taskkill', '/PID', str(browser.pid), '/T', '/F'], stdout=log, stderr=log, check=False, timeout=15)
                    REPORT['browser_cleanup_exit'] = completed.returncode
                    browser.wait(timeout=10)
                REPORT['browser_exited'] = browser.poll() is not None
        except Exception:
            REPORT['status'] = 'failed'
            REPORT['cleanup_error'] = traceback.format_exc()
        finally:
            if browser_log is not None:
                browser_log.close()
            save_report()
            DONE.set()


APP = qt.QApplication.instance()
TIMER = qt.QTimer(APP)
REPORT['qt_event_ticks'] = 0


def check_done():
    # Runs on Qt's main thread; the HTTP/RPC worker never waits on this thread.
    REPORT['qt_event_ticks'] += 1
    if not DONE.is_set():
        return
    TIMER.stop()
    if REPORT['status'] == 'awaiting_qt_validation':
        try:
            from PyQt6.QtSvg import QSvgRenderer
            REPORT['qt_svg'] = {}
            for svg in sorted((OUTPUT / 'suite').glob('*.svg')):
                renderer = QSvgRenderer(qt.QByteArray(svg.read_bytes()))
                if not renderer.isValid():
                    raise RuntimeError('Qt rejected ' + svg.name)
                size = renderer.defaultSize() * 3
                image = qt.QImage(size, qt.QImage.Format.Format_ARGB32)
                image.fill(qt.QColor('white'))
                painter = qt.QPainter(image)
                try:
                    renderer.render(painter)
                finally:
                    painter.end()
                png = OUTPUT / (svg.stem + '.png')
                if not image.save(str(png)):
                    raise RuntimeError('Could not save ' + png.name)
                REPORT['qt_svg'][svg.name] = {'valid': True, 'png': png.name,
                                              'width': image.width(), 'height': image.height()}
            REPORT['status'] = 'passed'
        except Exception:
            REPORT['status'] = 'failed'
            REPORT['qt_error'] = traceback.format_exc()
    save_report()
    APP.quit()


TIMER.timeout.connect(check_done)
TIMER.start(50)
WORKER = threading.Thread(target=work, name='veusz-browser-experiment', daemon=True)
WORKER.start()
