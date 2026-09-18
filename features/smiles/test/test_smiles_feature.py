"""Real QuickJS + Qt regressions, using only ../upstream-veusz.

Run: python features/smiles/test/test_smiles_feature.py
Outputs use inherited-ACL build-test-smiles, never a private temporary folder.
The parser examples test supported drawings, not chemical validation.
"""
import json
import math
import os
from pathlib import Path
import re
import sys
import unicodedata
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[3]
FEATURE = PROJECT / 'features' / 'smiles'
UPSTREAM = PROJECT.parent / 'upstream-veusz'
if not (UPSTREAM / 'veusz' / '__init__.py').is_file():
    raise RuntimeError('Tests require the explicit ../upstream-veusz checkout')
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(UPSTREAM))
os.environ['VEUSZ_JS_ENGINE_DEFER'] = '1'
os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if sys.platform == 'win32' else 'offscreen')

import veusz
import veusz.qtall as qt
import veusz.document
import veusz.setting
import veusz.setting.collections
import veusz.utils
import veusz.windows.mainwindow
import veusz_js_engine as engine

assert Path(veusz.__file__).resolve().is_relative_to(UPSTREAM.resolve())
APP = qt.QApplication.instance() or qt.QApplication([])
SVG = '{http://www.w3.org/2000/svg}'
OUT = PROJECT / 'build-test-smiles'


def font(family='Arial', size=20):
    return qt.QFont(family, size)


def image_stats(image):
    assert not image.isNull(), 'Qt could not read/render the exported image'
    ink = colored = 0
    xs, ys = [], []
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            if c.alpha() and min(c.red(), c.green(), c.blue()) < 245:
                ink += 1
                xs.append(x)
                ys.append(y)
                if max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) > 35:
                    colored += 1
    box = (max(xs)-min(xs)+1, max(ys)-min(ys)+1) if xs else (0, 0)
    return ink, colored, box


class SmilesFeatureTests(unittest.TestCase):
    def setUp(self):
        self.platform = engine.Platform(PROJECT)
        self.settings, self.hooks = {}, []
        # Real JsFeature hook and runtime; only capture registration and return
        # the reply rather than requiring a live page painter for unit tests.
        with patch.object(self.platform, 'add_setting', side_effect=lambda target, group, setting: self.settings.update({setting.name: setting})), \
             patch.object(self.platform, 'hook_draw', side_effect=lambda target, hook: self.hooks.append(hook)), \
             patch.object(self.platform, '_svg_renderer_class', return_value=lambda *a, **kw: kw['reply']):
            self.feature = engine.install_js_feature(self.platform, FEATURE / 'feature.js', FEATURE, 'smiles')
        self.runtime = self.feature.runtime
        self.addCleanup(self.runtime.close)

    def request(self, text, size=20, scale=1, colored=True, on=True, face=None, **extra):
        req = dict(text=text, size=size, color='#123456',
                   props=dict(on=on, scale=scale, colored=colored),
                   face=face or engine.text_font_key(qt, font()))
        req.update(extra)
        return req

    def call(self, req):
        raw = self.runtime.call('veuszRender', json.dumps(req))
        return json.loads(raw) if raw.strip() else None

    def first(self, req):
        for _ in range(4):
            reply = self.call(req)
            if not isinstance(reply, dict) or 'load' not in reply:
                return reply
            engine.load_feature_file(self.feature, reply['load'])
        self.fail('repeated deferred load requests')

    def render(self, text, label=None, **kwargs):
        label = label or font()
        req = self.request(text, face=engine.text_font_key(qt, label), **kwargs)
        reply = self.first(req)
        asked = reply.get('measure', []) if isinstance(reply, dict) else []
        if asked:
            req['measured'] = engine.measure_text_runs(qt, asked, label)
            reply = self.call(req)
        return reply, asked

    def valid_svg(self, reply):
        self.assertNotIn('error', reply, reply.get('error'))
        self.assertNotIn('measure', reply)
        for key in ('width', 'height'):
            self.assertTrue(math.isfinite(reply[key]) and reply[key] > 0)
        root = ET.fromstring(reply['svg'])
        tags = {node.tag.rsplit('}', 1)[-1] for node in root.iter()}
        self.assertFalse(tags & {'text', 'tspan', 'mask', 'rect', 'image'}, tags)
        self.assertTrue(tags & {'path', 'line', 'circle', 'polygon'}, 'no vector geometry')
        self.assertNotRegex(reply['svg'], r'\b(?:NaN|Infinity)\b')
        renderer = qt.QSvgRenderer(qt.QByteArray(reply['svg'].encode()))
        self.assertTrue(renderer.isValid())
        image = qt.QImage(500, 300, qt.QImage.Format.Format_ARGB32)
        image.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(image)
        renderer.render(painter)
        painter.end()
        self.assertGreater(image_stats(image)[0], 10)
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        return root

    def test_install_ui_and_off_empty_stay_cold(self):
        self.assertEqual(set(self.settings), {'smiles', 'smilesColored', 'smilesScale'})
        self.assertFalse(self.settings['smiles'].val)
        self.assertTrue(self.settings['smilesColored'].val)
        self.assertEqual(self.settings['smilesScale'].val, 1)
        self.assertFalse(self.settings['smiles'].hidden)
        self.assertTrue(self.settings['smilesColored'].hidden)
        control = self.settings['smiles'].makeControl(None)
        self.assertEqual(len(control.controls), 2)
        self.assertEqual(self.runtime.run('typeof globalThis.smilesToSvg'), 'undefined')
        with patch.object(self.runtime, 'eval_file', wraps=self.runtime.eval_file) as evaluate:
            for text, on in [('CCO', False), ('', True), (' \n\t ', True)]:
                self.assertIsNone(self.call(self.request(text, on=on)))
            evaluate.assert_not_called()
        self.assertFalse({Path(p).name for p in self.runtime.loaded_scripts} & {'headless.js', 'smiles-drawer.js'})

    def test_real_hook_loads_once_and_shapes_with_qt(self):
        self.settings['smiles'].val = True
        image = qt.QImage(500, 300, qt.QImage.Format.Format_ARGB32)
        painter = qt.QPainter(image)
        try:
            with patch.object(self.runtime, 'eval_file', wraps=self.runtime.eval_file) as evaluate, \
                 patch.object(engine, 'measure_text_runs', wraps=engine.measure_text_runs) as measure:
                result = self.hooks[0](painter, font(), 0, 0, 'CCO', self.settings)
                self.valid_svg(result)
                self.assertEqual([c.args[0].name for c in evaluate.call_args_list], ['headless.js', 'smiles-drawer.js'])
                self.assertEqual(measure.call_count, 1)
                self.assertTrue(any('O' in r['text'] for r in measure.call_args.args[1]))
                self.assertEqual(self.hooks[0](painter, font(), 0, 0, 'CCO', self.settings), result)
                self.assertEqual(measure.call_count, 1)
                self.assertEqual(evaluate.call_count, 2)
        finally:
            painter.end()

    def test_supported_molecules_produce_path_only_svg(self):
        for name, smiles in [('benzene', 'c1ccccc1'), ('ethanol', 'CCO'),
                             ('aspirin', 'CC(=O)Oc1ccccc1C(=O)O'),
                             ('charged-isotope', '[13CH3][NH3+]'),
                             ('chiral', 'N[C@@H](C)C(=O)O'),
                             ('alkene-stereo', 'F/C=C/F'),
                             ('opposite-alkene', 'F/C=C\\F')]:
            with self.subTest(molecule=name):
                reply, asked = self.render(smiles)
                self.valid_svg(reply)
                if name != 'benzene':
                    self.assertTrue(asked, 'heteroatoms must use the Qt measurement handshake')

    def test_atom_labels_are_real_qt_outline_paths(self):
        req = self.request('[13CH3][NH3+]')
        first = self.first(req)
        self.assertIn('measure', first)
        texts = unicodedata.normalize('NFKC', ''.join(r['text'] for r in first['measure']))
        for expected in ('N', 'H', '13'):
            self.assertIn(expected, texts)
        measured = engine.measure_text_runs(qt, first['measure'], font())
        self.assertTrue(measured)
        req['measured'] = measured
        reply = self.call(req)
        self.valid_svg(reply)
        # The library also measures bare element symbols as layout probes;
        # actual isotope/charge labels must use the Qt-produced outline data.
        paths = {n.get('d') for n in ET.fromstring(reply['svg']).iter(SVG + 'path')}
        outlined = 0
        for request in first['measure']:
            if any(c in request['text'] for c in ('¹', '³', '⁺', 'H')):
                outline = measured[request['key']]['path']
                self.assertTrue(outline)
                self.assertIn(outline, paths)
                outlined += 1
        self.assertGreaterEqual(outlined, 2)

    def test_trim_scaling_size_and_font_face_cache(self):
        base, asked = self.render('CCO')
        self.assertTrue(asked)
        cached, asked = self.render('  CCO \n')
        self.assertEqual(cached, base)
        self.assertFalse(asked)
        for opts in ({'scale': 2}, {'size': 40}):
            reply, _ = self.render('CCO', **opts)
            for dim in ('width', 'height'):
                self.assertAlmostEqual(reply[dim], base[dim] * 2, places=7)
        bold = font()
        bold.setBold(True)
        changed, asked = self.render('CCO', label=bold)
        self.assertTrue(asked, 'a different face must not reuse old glyphs')
        self.assertNotEqual(changed['svg'], base['svg'])
        again, asked = self.render('CCO', label=bold)
        self.assertFalse(asked)
        self.assertEqual(again, changed)

    def test_monochrome_and_element_colors(self):
        colored, _ = self.render('NCCO')
        mono, _ = self.render('NCCO', colored=False)
        self.valid_svg(colored)
        self.valid_svg(mono)
        self.assertNotEqual(colored['svg'], mono['svg'])
        self.assertIn('#123456', mono['svg'].lower())
        colors = set(re.findall(r'#[0-9a-fA-F]{6}', colored['svg']))
        self.assertGreaterEqual(len(colors), 2)
        self.assertAlmostEqual(colored['width'], mono['width'])
        self.assertAlmostEqual(colored['height'], mono['height'])
        # A new source defeats the feature cache: monochrome must not mutate
        # SmilesDrawer's shared theme defaults for subsequent colored drawings.
        fresh, _ = self.render('OCCCN')
        self.valid_svg(fresh)
        self.assertGreaterEqual(len(set(re.findall(r'#[0-9a-fA-F]{6}', fresh['svg']))), 2)
        self.assertNotIn('#123456', fresh['svg'].lower())

    def test_bad_input_limits_and_recovery(self):
        for source in ('C(', '[invalid', 'C)', 'C1CC', 'C11'):
            with self.subTest(source=source):
                self.assertIn('error', self.render(source)[0])
                self.valid_svg(self.render('CCO')[0])
        self.assertIn('error', self.first(self.request('C' * 4097)))
        self.assertIn('error', self.render('C' * 257)[0])
        for scale in (0, -1, 0.099, 10.01, 'NaN', 'Infinity'):
            with self.subTest(scale=scale):
                self.assertIn('error', self.first(self.request('CCO', scale=scale)))
        for scale in (0.1, 10):
            self.valid_svg(self.render('CCO', scale=scale)[0])
        self.assertIn('error', self.first(self.request('CCN', discard=True)))
        self.assertIn('error', self.first(self.request('CCN', measured={})))

    def test_nonfinite_geometry_is_an_error_not_an_svg(self):
        self.first(self.request('CCO'))
        self.runtime.run('globalThis.originalSmilesToSvg = globalThis.smilesToSvg;')
        try:
            # 1e400 is legal JSON but becomes Infinity when parsed by JS.
            for width in ('1e400', '0', '-1', 'null'):
                payload = '{"svg":"<svg/>","width":' + width + ',"height":20}'
                self.runtime.run('globalThis.smilesToSvg = function () { return ' + json.dumps(payload) + '; };')
                reply = self.call(self.request('NCCO'))
                self.assertIn('error', reply)
                self.assertNotIn('svg', reply)
        finally:
            self.runtime.run('globalThis.smilesToSvg = globalThis.originalSmilesToSvg;')
        self.valid_svg(self.render('NCCO')[0])


class UpstreamExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Never read/write the user's feature enablement preferences. Existing
        # upstream settings are copied in memory; its persistent write is unused.
        fake = dict(veusz.setting.settingdb.database)
        fake[engine.FEATURE_DISABLED_KEY] = []
        cls.preference_patch = patch.object(veusz.setting, 'settingdb', fake)
        cls.preference_patch.start()
        cls.addClassCleanup(cls.preference_patch.stop)
        cls.platform = engine.install(verbose=False)
        cls.feature = next(f for f in cls.platform.feature_objects() if f.name == 'smiles')
        OUT.mkdir(exist_ok=True)

    def test_real_page_png_svg_and_document_roundtrip(self):
        doc = veusz.document.Document()
        commands = veusz.document.CommandInterface(doc)
        page = commands.Add('page')
        commands.To(page)
        commands.Set('width', '10cm')
        commands.Set('height', '6cm')
        commands.Add('label', name='molecule')
        commands.Set('molecule/label', '[13CH3][NH3+]')
        commands.Set('molecule/Text/font', 'Arial')
        commands.Set('molecule/Text/size', '20pt')
        commands.Set('molecule/Text/smiles', True)
        commands.Set('molecule/Text/smilesColored', True)
        commands.Set('molecule/Text/smilesScale', 1.5)
        outputs = {}
        with patch.object(self.feature, 'render', wraps=self.feature.render) as render:
            for mode in (True, False):
                commands.Set('molecule/Text/smilesColored', mode)
                stem = 'colored' if mode else 'mono'
                for extension in ('png', 'svg'):
                    path = OUT / (stem + '.' + extension)
                    commands.Export(str(path), dpi=100)
                    self.assertTrue(path.is_file())
                    if extension == 'png':
                        outputs[stem] = image_stats(qt.QImage(str(path)))
                    else:
                        root = ET.parse(path).getroot()
                        self.assertTrue(list(root.iter(SVG + 'path')))
                        self.assertFalse(list(root.iter(SVG + 'text')))
                        self.assertFalse(list(root.iter(SVG + 'mask')))
                        self.assertTrue(qt.QSvgRenderer(str(path)).isValid())
            self.assertTrue(render.called, 'export did not reach the SMILES feature')
        self.assertGreater(outputs['colored'][0], 50)
        self.assertGreater(outputs['colored'][1], 10)
        self.assertEqual(outputs['mono'][1], 0)
        self.assertEqual(outputs['colored'][2], outputs['mono'][2])
        saved = OUT / 'smiles-roundtrip.vsz'
        commands.Save(str(saved))
        contents = saved.read_text(encoding='utf-8')
        for setting in ('smiles', 'smilesColored', 'smilesScale'):
            self.assertIn(setting, contents)
        restored = veusz.document.Document()
        # Upstream advertises optional FITS import commands even when astropy
        # is absent. Exclude only uninstalled commands; execute its real loader.
        interface = veusz.document.CommandInterface
        available = [name for name in interface.safe_commands if hasattr(interface, name)]
        with patch.object(interface, 'safe_commands', available):
            restored.load(str(saved))
        settings = restored.resolveWidgetPath(None, '/' + page + '/molecule').settings.Text
        self.assertTrue(settings.smiles)
        self.assertFalse(settings.smilesColored)
        self.assertEqual(settings.smilesScale, 1.5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
