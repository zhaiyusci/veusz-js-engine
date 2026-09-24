"""Disposable integration plugin for an installed Veusz. Never add to Preferences.
Run with test/run_browser_veusz.ps1; it exports a real document then exits.
"""
import json
import os
from pathlib import Path
import sys
import traceback
import xml.etree.ElementTree as ET

import veusz.document
import veusz.utils
from veusz import qtall as qt

SCRIPT = Path(sys.argv[sys.argv.index('--veusz-plugin') + 1]).resolve()
ROOT = SCRIPT.parent.parent
BROWSER_NAME = Path(os.environ.get('VEUSZ_JS_ENGINE_BROWSER', 'auto')).stem
OUT = ROOT / 'build-test-browser-veusz' / (os.environ.get('VEUSZ_JS_ENGINE_BACKEND', 'browser') + '-' + BROWSER_NAME)
OUT.mkdir(parents=True, exist_ok=True)
REPORT = {'status': 'running', 'host': sys.executable, 'python': sys.version,
          'frozen': bool(getattr(sys, 'frozen', False))}
APP = qt.QApplication.instance()


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    platform = None
    session = None
    try:
        os.environ.pop('VEUSZ_JS_ENGINE_DEFER', None)
        # Some installed builds already ship a native molecule3d widget. Use
        # fresh registrations ONLY in this disposable test process; production
        # deliberately refuses to replace an unrelated native widget type.
        REPORT['preexisting_widget_types'] = {}
        for name in ('smiles', 'molecule3d'):
            existing = veusz.document.thefactory.regwidgets.get(name)
            if existing is not None and not getattr(existing, '_js_engine_widget_entry', None):
                REPORT['preexisting_widget_types'][name] = existing.__module__
                veusz.document.thefactory.regwidgets.pop(name)
        veusz.document.Document.loadPlugins(pluginlist=[str(ROOT / 'veusz_js_engine.py')])
        platform = getattr(veusz.utils, 'js_engine')
        expected = os.environ.get('VEUSZ_JS_ENGINE_BACKEND', 'browser')
        check(platform.backend == expected, 'Unexpected backend')
        namespace = platform.feature_runtime.__func__.__globals__
        # Test all shipped features even if a user disabled one in Preferences.
        # Direct registration is confined to this disposable process, no settings write.
        installed = {feature.name: feature for feature in platform.feature_objects()}
        for name in ('mathjax', 'katex', 'smiles', 'molecule3d'):
            if name not in installed:
                directory = ROOT / 'features' / name
                installed[name] = namespace['install_js_feature'](
                    platform, directory / 'feature.js', directory, name)
        if expected == 'browser':
            check(platform.quickjs is None, 'Browser mode unexpectedly uses a QuickJS DLL')
            session = platform._browser_session
        font = qt.QFont('Arial', 20)
        cases = []

        def render(name, text, changes):
            feature = installed[name]
            props = {prop['name']: prop.get('default') for prop in feature.properties}
            props.update(changes)
            request = {'text': text, 'size': 20, 'color': '#102040', 'props': props,
                       'face': namespace['text_font_key'](qt, font)}
            loads, measurements = [], 0
            for step in range(64):
                raw = feature.runtime.call('veuszRender', json.dumps(request))
                check(bool(raw), name + ' declined unexpectedly')
                reply = json.loads(raw)
                check('error' not in reply, str(reply)[:500])
                if 'load' in reply:
                    loads.append(reply['load'])
                    namespace['load_feature_file'](feature, reply['load'])
                elif 'measure' in reply:
                    measurements += len(reply['measure'])
                    request['measured'] = namespace['measure_text_runs'](qt, reply['measure'], font)
                else:
                    if name != 'katex':
                        check('svg' in reply, name + ' produced no SVG')
                        ET.fromstring(reply['svg'])
                        (OUT / (name + '.svg')).write_text(reply['svg'], encoding='utf-8')
                    else:
                        check('delegate' in reply and '<math' in reply['delegate'],
                              'KaTeX did not delegate native MathML text')
                        (OUT / 'katex.json').write_text(json.dumps(reply, ensure_ascii=False, indent=2), encoding='utf-8')
                    cases.append({'feature': name, 'loads': loads, 'measured_runs': measurements,
                                  'reply_keys': list(reply)})
                    return reply
            raise RuntimeError(name + ' exceeded load/measure limit')

        mathjax = render('mathjax', r'\frac{x^2}{2}+\text{browser font}',
                         {'on': True, 'font': 'asana', 'display': True})
        check('data-veusz-text' in mathjax['svg'], 'Qt formula text outlines missing')
        check(cases[-1]['measured_runs'] > 0, 'MathJax skipped Qt measurement')
        render('katex', r'\sum_{n=1}^5 n', {'on': True, 'display': True})
        render('smiles', 'NCCO', {'smiles': 'NCCO', 'colored': True})
        render('molecule3d', 'water', {'model': 'water', 'labels': True})
        REPORT['cases'] = cases
        check(len({id(f.runtime._js) for f in installed.values()}) == 4,
              'Feature runtimes are not isolated')
        for name, feature in installed.items():
            check(json.loads(feature.runtime.call('veuszDescribe'))['name'] == name,
                  'Feature globals were overwritten by another runtime')

        # Exercise the real document paint/export seam, not just direct JS calls.
        document = veusz.document.Document()
        commands = veusz.document.CommandInterface(document)
        page = commands.Add('page')
        commands.To(page)
        commands.Set('width', '16cm')
        commands.Set('height', '12cm')
        commands.Add('label', name='formula')
        for setting, value in {'label': r'\int_0^1 x^2\,dx=\frac13\quad\text{Qt outlines}',
                               'xPos': [0.12], 'yPos': [0.84], 'Text/size': '20pt',
                               'Text/font': 'Arial', 'Text/mathjax': True,
                               'Text/mathjaxFont': 'asana', 'Text/mathjaxDisplay': True}.items():
            commands.Set('formula/' + setting, value)
        commands.Add('label', name='native')
        for setting, value in {'label': r'\sum_{n=1}^5 n=15', 'xPos': [0.12],
                               'yPos': [0.64], 'Text/size': '20pt', 'Text/katex': True}.items():
            commands.Set('native/' + setting, value)
        commands.Add('smiles', name='molecule')
        commands.Set('molecule/smiles', 'NCCO')
        commands.Set('molecule/xPos', [0.28])
        commands.Set('molecule/yPos', [0.30])
        commands.Add('molecule3d', name='water')
        commands.Set('water/model', 'water')
        commands.Set('water/labels', True)
        commands.Set('water/scale', 35.0)
        commands.Set('water/xPos', [0.74])
        commands.Set('water/yPos', [0.35])
        notes_before = list(platform.state.notes)
        commands.Save(str(OUT / 'browser-document.vsz'))
        commands.Export(str(OUT / 'browser-document.png'), dpi=120, backcolor='#ffffffff')
        commands.Export(str(OUT / 'browser-document.svg'), dpi=120)
        image = qt.QImage(str(OUT / 'browser-document.png'))
        check(not image.isNull(), 'Document PNG missing')
        ink = sum(1 for y in range(image.height()) for x in range(image.width())
                  if image.pixelColor(x, y).alpha() and
                  min(image.pixelColor(x, y).red(), image.pixelColor(x, y).green(), image.pixelColor(x, y).blue()) < 240)
        check(ink > 1000, 'Document export is blank')
        new_notes = [note for note in platform.state.notes if note not in notes_before]
        check(not new_notes, 'Document renderer reported errors: ' + str(new_notes))
        REPORT['document'] = {'width': image.width(), 'height': image.height(), 'ink_pixels': ink,
                              'new_notes': new_notes}
        REPORT['platform'] = platform.report()
        REPORT['status'] = 'passed'
    except Exception:
        REPORT['status'] = 'failed'
        REPORT['error'] = traceback.format_exc()
    finally:
        if platform is not None:
            platform.close_all()
        if session is not None:
            REPORT['browser_after_close'] = session.report()
            if REPORT['browser_after_close'].get('cleanup_errors'):
                REPORT['status'] = 'failed'
        (OUT / 'results.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        APP.quit()


qt.QTimer.singleShot(0, run)
