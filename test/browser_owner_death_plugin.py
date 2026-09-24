"""Disposable frozen-Veusz owner-death probe; never install in Preferences.

The runner kills the host only AFTER ready.json proves browser JavaScript ran.
No normal close/quit is performed on the successful path.
"""
import json
import os
from pathlib import Path
import sys
import traceback

import veusz.document
import veusz.utils
from veusz import qtall as qt

SCRIPT = Path(sys.argv[sys.argv.index('--veusz-plugin') + 1]).resolve()
ROOT = SCRIPT.parent.parent
BROWSER_NAME = Path(os.environ['VEUSZ_JS_ENGINE_BROWSER']).stem
OUT = ROOT / 'build-test-browser-owner-death' / ('Firefox' if BROWSER_NAME.lower() == 'firefox' else 'msedge')
OUT.mkdir(parents=True, exist_ok=True)
APP = qt.QApplication.instance()
PLATFORM = None
SESSION = None


def publish(name, value):
    temporary = OUT / (name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(OUT / name)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    global PLATFORM, SESSION
    report = {'veusz_pid': os.getpid(), 'host': sys.executable,
              'frozen': bool(getattr(sys, 'frozen', False)), 'python': sys.version}
    try:
        check(report['frozen'], 'This probe must run inside installed frozen Veusz')
        APP.setQuitOnLastWindowClosed(False)
        os.environ.pop('VEUSZ_JS_ENGINE_DEFER', None)
        # Registration changes are in-memory only, never saved to user prefs.
        for name in ('smiles', 'molecule3d'):
            existing = veusz.document.thefactory.regwidgets.get(name)
            if existing is not None and not getattr(existing, '_js_engine_widget_entry', None):
                veusz.document.thefactory.regwidgets.pop(name)
        veusz.document.Document.loadPlugins(pluginlist=[str(ROOT / 'veusz_js_engine.py')])
        PLATFORM = getattr(veusz.utils, 'js_engine')
        check(PLATFORM.backend == 'browser', 'Expected browser backend')
        check(PLATFORM.quickjs is None, 'Unexpected native QuickJS backend')
        features = {feature.name: feature for feature in PLATFORM.feature_objects()}
        if 'mathjax' not in features:
            namespace = PLATFORM.feature_runtime.__func__.__globals__
            directory = ROOT / 'features' / 'mathjax'
            features['mathjax'] = namespace['install_js_feature'](
                PLATFORM, directory / 'feature.js', directory, 'mathjax')
        # A browser RPC round trip, not just inspection of Python metadata.
        raw = features['mathjax'].runtime.call('veuszDescribe')
        description = json.loads(raw)
        check(description['name'] == 'mathjax', 'MathJax JS execution returned wrong feature')
        SESSION = PLATFORM._browser_session
        session_report = SESSION.report()  # Public report deliberately excludes credentials.
        lifetime = session_report['process_lifetime']
        check(lifetime['mechanism'] == 'windows-job-object', 'Expected Windows Job Object')
        check(lifetime.get('atomic_job_assignment') is True, 'Job assignment was not atomic')
        check(session_report['connected'], 'Browser session disconnected')
        check(session_report['pid'] == SESSION._pid and SESSION._pid > 0, 'Missing browser root PID')
        check(session_report['temporary_directory'] == str(SESSION._temp_path), 'Missing isolated profile')
        report.update(status='ready', session=session_report,
                      js_result={'function': 'veuszDescribe', 'raw': raw, 'parsed': description})
        publish('ready.json', report)
        # Qt event loop stays alive; the runner alone triggers abnormal host death.
    except Exception:
        report.update(status='failed', error=traceback.format_exc())
        try:
            if PLATFORM is not None:
                PLATFORM.close_all()
        except Exception:
            report['close_error'] = traceback.format_exc()
        finally:
            try:
                publish('failed.json', report)
            finally:
                APP.quit()


qt.QTimer.singleShot(0, run)
