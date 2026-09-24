"""Real JavaScript/Qt standalone molecule3d regressions (only ../upstream-veusz).

Run with user-site Qt enabled: python features/molecule3d/test/test_molecule3d_feature.py
Backend follows VEUSZ_JS_ENGINE_BACKEND: browser by default, or explicit quickjs.
Fixtures/exports inherit workspace ACLs under build-test-molecule3d.
No upstream files or user preferences are modified.
"""
import base64
import copy
import json
import math
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[3]
FEATURE = PROJECT / 'features' / 'molecule3d'
UPSTREAM = PROJECT.parent / 'upstream-veusz'
if not (UPSTREAM / 'veusz' / '__init__.py').is_file():
    raise RuntimeError('Tests require the explicit ../upstream-veusz checkout')
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(UPSTREAM))
os.environ['VEUSZ_JS_ENGINE_DEFER'] = '1'
os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if sys.platform == 'win32' else 'offscreen')

import veusz
import veusz.qtall as qt


class MemoryQSettings:
    def __init__(self, *args, **kwargs):
        self.values = {}

    def childKeys(self):
        return list(self.values)

    def value(self, key):
        return self.values[key]

    def setValue(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)


with patch.object(qt, 'QSettings', MemoryQSettings):
    import veusz.document
    import veusz.setting
    import veusz.setting.collections
    import veusz.utils
    import veusz.windows.mainwindow
import veusz_js_engine as engine

assert Path(veusz.__file__).resolve().is_relative_to(UPSTREAM.resolve())
APP = qt.QApplication.instance() or qt.QApplication([])
SVG = '{http://www.w3.org/2000/svg}'
OUT = PROJECT / 'build-test-molecule3d'
BUNDLES = ['dot-regions.js', 'boundaries.js', 'wash.js', 'dots.js', 'renderer.js']
WATER = '3\nEmbedded water\nO 0 0 0\nH 0.9572 0 0\nH -0.239987 0.927297 0\n'


def image_stats(image):
    assert not image.isNull(), 'Qt could not read/render the image'
    ink = colored = opaque = 0
    xs, ys = [], []
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            if c.alpha() == 255:
                opaque += 1
            if c.alpha() and min(c.red(), c.green(), c.blue()) < 245:
                ink += 1
                xs.append(x)
                ys.append(y)
                if max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) > 35:
                    colored += 1
    box = (max(xs)-min(xs)+1, max(ys)-min(ys)+1) if xs else (0, 0)
    return ink, colored, box, opaque


class Molecule3dTests(unittest.TestCase):
    def setUp(self):
        self.platform = engine.Platform(PROJECT)
        registry = patch.dict(veusz.document.thefactory.regwidgets)
        registry.start()
        self.addCleanup(registry.stop)
        veusz.document.thefactory.regwidgets.pop('molecule3d', None)
        self.feature = engine.install_js_feature(self.platform, FEATURE / 'feature.js', FEATURE, 'molecule3d')
        self.runtime = self.feature.runtime
        self.addCleanup(self.platform.close_all)
        self.doc = veusz.document.Document()
        self.commands = veusz.document.CommandInterface(self.doc)
        self.page = self.commands.Add('page')
        self.commands.To(self.page)
        self.commands.Add('molecule3d', name='molecule')
        self.widget = self.doc.resolveWidgetPath(None, '/' + self.page + '/molecule')
        self.settings = self.widget.settings
        self.defaults = {prop['name']: prop.get('default') for prop in self.feature.properties}
        OUT.mkdir(exist_ok=True)

    def request(self, props=None, label=None, color='#123456', **extra):
        values = dict(self.defaults)
        values.update(props or {})
        req = dict(text='not the XYZ source', size=12, color=color, props=values,
                   face=engine.text_font_key(qt, label or qt.QFont('Arial', 12)))
        req.update(extra)
        return req

    def call(self, req):
        raw = self.runtime.call('veuszRender', json.dumps(req))
        return json.loads(raw) if raw.strip() else None

    def first(self, req):
        for _ in range(7):
            reply = self.call(req)
            if not isinstance(reply, dict) or 'load' not in reply:
                return reply
            engine.load_feature_file(self.feature, reply['load'])
        self.fail('repeated deferred load requests')

    def render(self, props=None, label=None, **extra):
        label = label or qt.QFont('Arial', 12)
        req = self.request(props, label=label, **extra)
        reply = self.first(req)
        asked = reply.get('measure', []) if isinstance(reply, dict) else []
        if asked:
            req['measured'] = engine.measure_text_runs(qt, asked, label)
            reply = self.call(req)
        return reply, asked

    def valid_svg(self, reply):
        self.assertIsInstance(reply, dict)
        self.assertNotIn('error', reply, reply.get('error'))
        self.assertNotIn('measure', reply)
        for dimension in ('width', 'height'):
            self.assertTrue(math.isfinite(reply[dimension]) and reply[dimension] > 0)
        root = ET.fromstring(reply['svg'])
        tags = {node.tag.rsplit('}', 1)[-1] for node in root.iter()}
        self.assertFalse(tags & {'text', 'tspan', 'script', 'foreignObject'}, tags)
        self.assertTrue(tags & {'path', 'circle', 'ellipse', 'polygon', 'line'})
        self.assertNotRegex(reply['svg'], r'\b(?:NaN|Infinity)\b')
        # Shared stipple tiles may be embedded PNGs, never external images or
        # arbitrary data documents. Non-image references must stay within SVG.
        for node in root.iter():
            refs = [value for name, value in node.attrib.items()
                    if name.rsplit('}', 1)[-1] in ('href', 'src')]
            if node.tag == SVG + 'image':
                self.assertTrue(refs, 'embedded image must have an explicit PNG data URI')
                for value in refs:
                    self.assertTrue(value.startswith('data:image/png;base64,'), value[:100])
                    png = base64.b64decode(value.split(',', 1)[1], validate=True)
                    self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
                    self.assertFalse(qt.QImage.fromData(png, 'PNG').isNull())
            else:
                for value in refs:
                    self.assertTrue(value.startswith('#'), 'external SVG reference: ' + value[:100])
        for reference in re.findall(r'url\(([^)]+)\)', reply['svg']):
            self.assertTrue(reference.strip('\"\' ').startswith('#'), reference)
        renderer = qt.QSvgRenderer(qt.QByteArray(reply['svg'].encode()))
        self.assertTrue(renderer.isValid())
        image = qt.QImage(320, 240, qt.QImage.Format.Format_ARGB32)
        image.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(image)
        renderer.render(painter)
        painter.end()
        self.assertGreater(image_stats(image)[0], 20)
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0, 'canvas background must be transparent')
        self.assertGreater(image_stats(image)[3], 20, 'opaque atom/bond bodies must be preserved')
        return root, image

    def draw(self, pagesize=(500, 300), dpi=96):
        helper = veusz.document.PaintHelper(self.doc, pagesize, dpi=(dpi, dpi))
        self.widget.draw([0, 0, *pagesize], helper)
        return helper

    def painted(self, pagesize=(500, 300), dpi=96):
        helper = self.draw(pagesize, dpi)
        image = qt.QImage(*pagesize, qt.QImage.Format.Format_ARGB32)
        image.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(image)
        helper.renderToPainter(painter)
        painter.end()
        return image, helper

    def test_declaration_native_settings_and_cold_hidden_empty(self):
        declaration = json.loads(self.runtime.call('veuszDescribe', ''))
        for name, value in [('name', 'molecule3d'), ('target', 'widget'), ('source', 'model'),
                            ('sizing', 'natural'), ('version', '0.3.1')]:
            self.assertEqual(declaration[name], value)
        self.assertEqual(self.settings.model, 'water')
        self.assertEqual(self.settings.xyz, '')
        self.assertEqual(self.settings.scale, 18)
        self.assertEqual(self.settings.atomRadiusScale, .75)
        self.assertTrue(self.settings.labelHydrogens)
        self.assertEqual(self.settings.shading, self.defaults['shading'])
        for name in ('xyz', 'model', 'font', 'color', 'xPos', 'yPos', 'rotate', 'hide'):
            self.assertIn(name, self.settings)
        self.assertEqual(self.settings.shading, 'hatch')
        levels = self.settings.get('shadingLevels')
        self.assertIsInstance(levels, veusz.setting.Choice)
        self.assertEqual(list(levels.vallist), ['4', '8', '16', '32', '64'])
        for name, expected in [('shadingLevels', '16'), ('shadingBrightness', 0),
                               ('shadingContrast', 1.2)]:
            self.assertEqual(self.defaults[name], expected)
            self.assertEqual(getattr(self.settings, name), expected)
            self.assertIs(self.settings.get(name).parent, self.settings)
        self.assertIsInstance(self.defaults['shadingLevels'], str)
        for name in ('shadingBrightness', 'shadingContrast'):
            self.assertIsInstance(self.settings.get(name), veusz.setting.Float)
        mode = self.settings.get('renderMode')
        self.assertIsInstance(mode, veusz.setting.Choice)
        self.assertEqual(list(mode.vallist), ['precise', 'fast'])
        self.assertIsInstance(self.settings.get('castShadows'), veusz.setting.Bool)
        self.assertIsInstance(self.settings.get('shadowStrength'), veusz.setting.Float)
        for name, expected in [('renderMode', 'precise'), ('castShadows', False),
                               ('shadowStrength', .8)]:
            self.assertEqual(self.defaults[name], expected)
            self.assertEqual(getattr(self.settings, name), expected)
            self.assertIs(self.settings.get(name).parent, self.settings)
        for name in ('fast', 'shadows'):
            self.assertNotIn(name, self.defaults)
        for name in ('Text', 'size', 'width', 'height', 'fast', 'shadows'):
            self.assertNotIn(name, self.settings)
        text = veusz.setting.collections.Text('Text')
        self.assertNotIn('molecule3d', text)
        with patch.object(self.runtime, 'eval_file', wraps=self.runtime.eval_file) as evaluate:
            self.settings.get('hide').set(True)
            self.draw()
            self.settings.get('hide').set(False)
            self.settings.get('model').set('xyz')
            for source in ('', ' \n\t '):
                self.assertIsNone(self.call(self.request({'model': 'xyz', 'xyz': source})))
                self.settings.get('xyz').set(source)
                self.draw()
            evaluate.assert_not_called()
        self.assertFalse(set(BUNDLES) & {Path(p).name for p in self.runtime.loaded_scripts})

    def test_legacy_request_without_new_settings_defaults_to_precise(self):
        expected, _ = self.render()
        req = self.request()
        for name in ('renderMode', 'castShadows', 'shadowStrength'):
            del req['props'][name]
        self.assertEqual(self.first(req), expected)
        self.valid_svg(expected)

    def test_bundles_load_in_order_once_and_runtime_is_offline(self):
        with patch.object(self.runtime, 'eval_file', wraps=self.runtime.eval_file) as evaluate:
            reply, _ = self.render({})
            self.valid_svg(reply)
            self.assertEqual([Path(c.args[0]).name for c in evaluate.call_args_list], BUNDLES)
            self.assertEqual(self.render({})[0], reply)
            self.assertEqual(evaluate.call_count, len(BUNDLES))
        # Network/browser APIs must not be provided by this headless runtime.
        self.assertEqual(self.runtime.run('typeof fetch + "," + typeof XMLHttpRequest + "," + typeof WebSocket'),
                         'undefined,undefined,undefined')

    def test_renderer_mode_and_effective_shadows_keep_export_contract(self):
        self.render()
        self.runtime.run('''
            globalThis.originalMoleculeRender = MolEngraver.render;
            globalThis.capturedMoleculeOptions = [];
            MolEngraver.render = function(molecule, options) {
                capturedMoleculeOptions.push(JSON.parse(JSON.stringify(options)));
                return originalMoleculeRender(molecule, options);
            };
        ''')
        try:
            cases = [{}, {'renderMode': 'precise', 'castShadows': True, 'shadowStrength': .6},
                     {'renderMode': 'fast', 'castShadows': True, 'shadowStrength': .35},
                     {'renderMode': 'fast', 'castShadows': False, 'shadowStrength': 1},
                     {'renderMode': 'fast', 'labels': True}]
            for index, injected in enumerate(cases):
                props = dict(injected, yaw=27 + index, fast=False, shadows=True,
                             lightType='point', quality='preview', quantizeShading=False,
                             stippleFill='marks')
                self.valid_svg(self.render(props)[0])
            options = json.loads(self.runtime.run('JSON.stringify(capturedMoleculeOptions)'))
            self.assertEqual(len(options), len(cases))
            for opts, props in zip(options, cases):
                mode = props.get('renderMode', 'precise')
                self.assertEqual(opts['renderMode'], mode)
                # Precise requests certified opaque surface ownership even when
                # user labels are hidden; the adapter strips internal text.
                self.assertIs(opts['labels'], mode == 'precise' or props.get('labels', False))
                self.assertNotIn('lightType', opts)
                self.assertIs(opts['castShadows'], mode == 'precise' and props.get('castShadows', False))
                self.assertEqual(opts['shadowStrength'], props.get('shadowStrength', .8))
                self.assertEqual(opts['quality'], 'export')
                self.assertIs(opts['quantizeShading'], True)
                self.assertEqual(opts['stippleFill'], 'bitmap')
                self.assertIs(type(opts['shadingLevels']), int)
                self.assertEqual(opts['shadingLevels'], 16)
                self.assertEqual(opts['shadingBrightness'], 0)
                self.assertEqual(opts['shadingContrast'], 1.2)
        finally:
            self.runtime.run('MolEngraver.render = originalMoleculeRender;')

    def test_default_precise_visible_regions_and_qt_overlap_occlusion(self):
        # The atoms are 3 A apart (no inferred bond), but concentric on screen.
        # Rear carbon is larger than front oxygen: both its visible ring and the
        # front red disk must survive exact depth clipping, irrespective of order.
        props = {'model': 'xyz', 'xyz': '2\noverlap\nC 0 0 -1.5\nO 0 0 1.5\n',
                 'pitch': 0, 'yaw': 0, 'roll': 0, 'scale': 60,
                 'shading': 'none', 'labels': False}
        reply, _ = self.render(props)  # Deliberately exercise the NEW default.
        root, image = self.valid_svg(reply)
        fills = [n for n in root.iter(SVG + 'path') if n.get('data-role') == 'surface-fill']
        self.assertEqual(len(fills), 2, 'precise visible surfaces must be vector paths')
        self.assertFalse([n for n in root.iter(SVG + 'circle')
                          if n.get('data-role') == 'surface-fill'])
        center = image.pixelColor(160, 120)
        self.assertEqual(center.alpha(), 255)
        self.assertGreater(center.red(), center.green() + 100, 'rear carbon painted over front oxygen')
        # Natural SVG units: O radius .66*.75*60/.75 = 39.6;
        # C radius .76*.75*60/.75 = 45.6. Sample the middle of its visible ring.
        view_width = float(root.get('width'))
        ring = image.pixelColor(round(160 + 42.6 * 320 / view_width), 120)
        self.assertEqual(ring.alpha(), 255)
        self.assertLess(abs(ring.red() - ring.green()), 5)
        self.assertGreater(ring.red(), 100)
        self.assertLess(ring.red(), 200)
        reversed_reply, _ = self.render(dict(props, xyz='2\noverlap\nO 0 0 1.5\nC 0 0 -1.5\n'))
        _, reversed_image = self.valid_svg(reversed_reply)
        self.assertEqual(image, reversed_image, 'visibility must not depend on XYZ atom order')
        labeled, _ = self.render(dict(props, labels=True))
        label_root, _ = self.valid_svg(labeled)
        self.assertEqual({n.get('data-surface-id') for n in label_root.iter(SVG + 'g')
                          if n.get('data-role') == 'element-label'}, {'1'},
                         'hidden carbon center must not acquire a floating label')

    def test_uncertified_precise_surfaces_report_visible_error_and_recover(self):
        self.render({'yaw': 17})  # Load bundles without caching the failing request.
        self.settings.yaw = 43
        self.runtime.run('''
            globalThis.originalMoleculeRender = MolEngraver.render;
            MolEngraver.render = function(molecule, options) {
                return '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'+
                    '<circle cx="100" cy="100" r="10" fill="white"/></svg>';
            };
        ''')
        try:
            reply, asked = self.render({'yaw': 43})
            self.assertFalse(asked)
            self.assertIn('error', reply)
            self.assertIn('certified', reply['error'])
            self.assertIn('fast', reply['error'])
            with patch.object(self.platform.state, 'note') as note:
                image, _ = self.painted()
                self.assertTrue(note.called)
                self.assertGreater(image_stats(image)[0], 20, 'certification failure must paint a visible error')
        finally:
            self.runtime.run('MolEngraver.render = originalMoleculeRender;')
        self.valid_svg(self.render({'yaw': 43})[0])
        with patch.object(self.platform.state, 'note') as note:
            image, _ = self.painted()
            note.assert_not_called()
            self.assertGreater(image_stats(image)[0], 20)

    def test_precise_nonhatch_white_atoms_and_bonds_are_opaque_without_labels(self):
        # White H bodies and the exposed bond used to rely on upstream's white
        # canvas in non-hatch modes. Removing that canvas must not punch holes
        # through uninked parts of these surfaces on a transparent Qt target.
        props = {'model': 'xyz', 'xyz': '2\nwhite bodies\nH -.37 0 0\nH .37 0 0\n',
                 'pitch': 0, 'yaw': 0, 'roll': 0, 'scale': 48,
                 'labels': False, 'colored': True, 'shadingBrightness': .5}
        for style in ('stipple', 'halftone'):
            with self.subTest(style=style):
                reply, asked = self.render(dict(props, shading=style))
                self.assertFalse(asked, 'internal ownership labels must not request Qt glyphs')
                root, image = self.valid_svg(reply)
                self.assertFalse([n for n in root.iter(SVG + 'g')
                                  if n.get('data-role') == 'element-label'])
                fills = [n for n in root.iter(SVG + 'path')
                         if n.get('data-role') == 'surface-fill']
                self.assertEqual(len(fills), 3, 'two atom regions and their exposed bond need opaque bodies')
                width, height = float(root.get('width')), float(root.get('height'))
                for center, radius in ((-.37, .07), (.37, .07), (0, .04)):
                    pixels = [image.pixelColor(
                        round(160 + (center + dx * radius / 2) * 64 * 320 / width),
                        round(120 + dy * radius / 2 * 64 * 240 / height))
                        for dy in range(-2, 3) for dx in range(-2, 3)]
                    self.assertTrue(all(c.alpha() == 255 for c in pixels),
                                    'precise %s left transparent holes at x=%s' % (style, center))
                    self.assertTrue(any(min(c.red(), c.green(), c.blue()) > 200 for c in pixels),
                                    'white paper must remain visible inside atom/bond bodies')

    def test_precise_shadow_pixels_toggle_strength_and_mode_cache_restore(self):
        # Light along +x/+z hits the receiver behind the raised, offset atom.
        # Large enough to rasterize real shadow ink, small enough for local contours.
        props = {'model': 'xyz', 'xyz': '2\nshadow\nC 0 0 0\nO .9 0 1.5\n',
                 'pitch': 0, 'yaw': 0, 'roll': 0, 'scale': 48,
                 'lightAzimuth': 31, 'lightElevation': 0,
                 'colored': False, 'shading': 'hatch', 'labels': False,
                 'shadowStrength': 1}
        plain, _ = self.render(props)
        shadow, _ = self.render(dict(props, castShadows=True))
        _, plain_image = self.valid_svg(plain)
        _, shadow_image = self.valid_svg(shadow)
        self.assertNotEqual(plain['svg'], shadow['svg'])
        changed_pixels = sum(plain_image.pixelColor(x, y) != shadow_image.pixelColor(x, y)
                             for y in range(240) for x in range(320))
        self.assertGreater(changed_pixels, 20, 'Qt dropped the precise shadow masks')
        zero, _ = self.render(dict(props, castShadows=True, shadowStrength=0))
        _, zero_image = self.valid_svg(zero)
        self.assertEqual(zero_image, plain_image, 'zero strength must not cast a visible shadow')
        fast, _ = self.render(dict(props, renderMode='fast', castShadows=True))
        _, fast_image = self.valid_svg(fast)
        fast_off, _ = self.render(dict(props, renderMode='fast', castShadows=False, shadowStrength=0))
        _, fast_off_image = self.valid_svg(fast_off)
        # Inactive strength can enter upstream's deterministic definition IDs;
        # compare actual pixels, not serialized IDs, for effective equivalence.
        self.assertEqual(fast_image, fast_off_image, 'fast must ignore saved shadow controls')
        self.assertNotEqual(fast['svg'], shadow['svg'])
        # Returning to precise must restore saved strength/switch, not reuse fast.
        for changes, expected in [({'castShadows': True}, shadow), ({}, plain),
                                  ({'renderMode': 'fast', 'castShadows': True}, fast),
                                  ({'castShadows': True}, shadow)]:
            self.assertEqual(self.render(dict(props, **changes))[0], expected)

    def test_all_levels_and_styles_pass_numeric_upstream_options(self):
        self.render()
        self.runtime.run('''
            globalThis.originalMoleculeRender = MolEngraver.render;
            globalThis.capturedMoleculeOptions = [];
            MolEngraver.render = function(molecule, options) {
                capturedMoleculeOptions.push(JSON.parse(JSON.stringify(options)));
                return originalMoleculeRender(molecule, options);
            };
        ''')
        try:
            for style in ('hatch', 'stipple', 'halftone'):
                for level in ('4', '8', '16', '32', '64'):
                    with self.subTest(style=style, level=level):
                        self.valid_svg(self.render({'shading': style, 'shadingLevels': level,
                                                   'shadingBrightness': .25,
                                                   'shadingContrast': 1.75})[0])
            captured = json.loads(self.runtime.run('JSON.stringify(capturedMoleculeOptions)'))
            self.assertEqual(len(captured), 15)
            for opts, (style, level) in zip(captured, ((s, n)
                    for s in ('hatch', 'stipple', 'halftone') for n in (4, 8, 16, 32, 64))):
                self.assertEqual(opts['shadingMode'], style)
                self.assertIs(type(opts['shadingLevels']), int)
                self.assertEqual(opts['shadingLevels'], level)
                self.assertEqual(opts['shadingBrightness'], .25)
                self.assertEqual(opts['shadingContrast'], 1.75)
                self.assertNotIn('lightType', opts)
                self.assertEqual(opts['renderMode'], 'precise')
                self.assertEqual(opts['quality'], 'export')
                self.assertIs(opts['castShadows'], False)
                self.assertIs(opts['quantizeShading'], True)
                self.assertEqual(opts['stippleFill'], 'bitmap')
        finally:
            self.runtime.run('MolEngraver.render = originalMoleculeRender;')

    def test_invalid_shading_options_report_errors_and_recover(self):
        baseline, _ = self.render()
        invalid = {
            'shadingLevels': ('0', '3', '128', '', 16, None, True),
            'shadingBrightness': (-1.01, 1.01, '0', None, True),
            'shadingContrast': (.49, 2.51, '1.2', None, False),
            'renderMode': ('', 'PRECISE', 'preview', 0, None, True),
            'castShadows': (0, 1, 'false', '', None),
            'shadowStrength': (-.01, 1.01, '0.8', None, True, False),
        }
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    reply = self.first(self.request({name: value}))
                    self.assertIn('error', reply)
                    self.assertIn(name, reply['error'])
                    self.assertEqual(self.render()[0], baseline)
        # Inactive fast shadow settings remain strictly typed/range checked;
        # otherwise switching back to precise would revive malformed saved data.
        for name in ('castShadows', 'shadowStrength'):
            for value in invalid[name]:
                with self.subTest(mode='fast', name=name, value=value):
                    reply = self.first(self.request({'renderMode': 'fast', name: value}))
                    self.assertIn('error', reply)
                    self.assertIn(name, reply['error'])
        for brightness, contrast in ((-1, .5), (1, 2.5)):
            self.valid_svg(self.render({'shadingBrightness': brightness,
                                       'shadingContrast': contrast})[0])
        # Bypass native normalization to simulate malformed saved/plugin data.
        # The draw path must paint a visible nonfatal error, then recover.
        for name, value in [('shadingLevels', '3'), ('shadingBrightness', 2),
                            ('shadingContrast', 0), ('renderMode', 'preview'),
                             ('castShadows', 1), ('shadowStrength', 2)]:
            setting = self.settings.get(name)
            with patch.object(setting, '_val', value), patch.object(setting, '_ref', None), \
                 patch.object(self.platform.state, 'note') as note:
                image, _ = self.painted()
                self.assertTrue(note.called)
                self.assertGreater(image_stats(image)[0], 20)
            with patch.object(self.platform.state, 'note') as note:
                image, _ = self.painted()
                note.assert_not_called()
                self.assertGreater(image_stats(image)[0], 20)

    def test_shading_options_cache_switch_and_restore(self):
        for style in ('hatch', 'stipple', 'halftone'):
            props = {'shading': style, 'colored': False}
            base, _ = self.render(props)
            for changes in ({'shadingLevels': '4'}, {'shadingLevels': '64'},
                            {'shadingBrightness': .4}, {'shadingContrast': 2}):
                with self.subTest(style=style, changes=changes):
                    changed, _ = self.render(dict(props, **changes))
                    self.valid_svg(changed)
                    self.assertNotEqual(changed['svg'], base['svg'])
                    self.assertEqual(self.render(props)[0], base)
                    self.assertEqual(self.render(dict(props, **changes))[0], changed)

    def test_water_ethanol_and_c60_are_real_qt_drawings(self):
        for model in ('water', 'ethanol', 'c60'):
            with self.subTest(model=model):
                reply, _ = self.render({'model': model})
                root, _ = self.valid_svg(reply)
                self.assertGreater(len(list(root.iter())), 4)

    def test_dense_c60_stipple_uses_embedded_bitmap_tiles_and_real_qt_ink(self):
        # Fixed reproduction of the user document, without reading user files:
        # default 18 pt/A, finest texture, mono C60, precise shadows, 16 levels.
        self.assertEqual(self.defaults['scale'], 18)
        props = {'model': 'c60', 'shading': 'stipple', 'textureScale': .2,
                 'colored': False, 'castShadows': True, 'shadingLevels': '16'}
        reply, asked = self.render(props)
        self.assertFalse(asked)
        root, image = self.valid_svg(reply)
        self.assertEqual(root.get('data-stipple-mode'), 'bitmap')
        images = list(root.iter(SVG + 'image'))
        self.assertTrue(images, 'dense stipple must reuse embedded PNG tiles')
        self.assertLess(len(reply['svg'].encode('utf-8')), 16 * 1024 * 1024,
                        'fix tile representation rather than raising the SVG budget')
        self.assertLess(len(list(root.iter(SVG + 'circle'))), 1000,
                        'dense C60 must not expand shared stipple into individual dot circles')
        flat, _ = self.render(dict(props, shading='none'))
        _, flat_image = self.valid_svg(flat)
        changed = ink_gain = 0
        for y in range(image.height()):
            for x in range(image.width()):
                stippled, plain = image.pixelColor(x, y), flat_image.pixelColor(x, y)
                changed += stippled != plain
                ink_gain += ((765 - stippled.red() - stippled.green() - stippled.blue()) * stippled.alpha()
                             - (765 - plain.red() - plain.green() - plain.blue()) * plain.alpha()) / 255
        self.assertGreater(changed, 100, 'Qt silently discarded embedded stipple tiles')
        self.assertGreater(ink_gain, 100 * 765,
                           'bitmap stipple must add visible ink, not merely valid SVG metadata')

    def test_shading_element_patterns_and_palette_have_real_qt_ink(self):
        outputs = []
        for shading in ('hatch', 'stipple', 'halftone', 'none'):
            reply, _ = self.render({'shading': shading})
            self.valid_svg(reply)
            outputs.append(reply['svg'])
        self.assertEqual(len(set(outputs)), 4)
        textured, _ = self.render({'shading': 'halftone', 'elementTextures': True})
        self.valid_svg(textured)
        self.assertNotEqual(textured['svg'], outputs[2])
        for palette in ('rasmol', 'pymol', 'ortep'):
            self.valid_svg(self.render({'palette': palette})[0])

    def test_qt_shading_is_confined_to_single_atom_silhouette(self):
        # Single carbon removes bond/overlap ambiguity. At 48pt/angstrom its
        # covalent radius is .76 * 48/.75 SVG px; the remaining margin is clear.
        # Rasterize at an explicit square target to avoid an aspect-ratio trap.
        props = {'model': 'xyz', 'xyz': '1\ncarbon\nC 0 0 0\n',
                 'scale': 48, 'atomRadiusScale': 1, 'colored': False, 'labels': False}
        interior_ink = {}
        cases = [(style, '16') for style in ('none', 'hatch', 'stipple')]
        cases += [('halftone', level) for level in ('4', '8', '16', '32', '64')]
        for style, level in cases:
            with self.subTest(style=style, level=level):
                reply, _ = self.render(dict(props, shading=style, shadingLevels=level))
                self.assertNotIn('error', reply)
                renderer = qt.QSvgRenderer(qt.QByteArray(reply['svg'].encode()))
                self.assertTrue(renderer.isValid())
                view = renderer.viewBoxF()
                self.assertAlmostEqual(view.width(), view.height(), places=6)
                raster_scale = 256 / view.width()
                radius = .76 * 48 / .75 * raster_scale
                # The .8 SVG-px silhouette stroke extends half its width past
                # the physical radius. Allow only one extra antialias pixel.
                outer_radius = radius + .4 * raster_scale + 1
                image = qt.QImage(256, 256, qt.QImage.Format.Format_ARGB32)
                image.fill(qt.Qt.GlobalColor.transparent)
                painter = qt.QPainter(image)
                renderer.render(painter, qt.QRectF(0, 0, 256, 256))
                painter.end()
                leaked = dark_inside = light_inside = 0
                for y in range(256):
                    for x in range(256):
                        pixel = image.pixelColor(x, y)
                        distance = math.hypot(x + .5 - 128, y + .5 - 128)
                        if distance > outer_radius and pixel.alpha() > 32:
                            leaked += 1
                        if distance < radius * .85 and pixel.alpha() > 128:
                            if max(pixel.red(), pixel.green(), pixel.blue()) < 100:
                                dark_inside += 1
                            if min(pixel.red(), pixel.green(), pixel.blue()) > 200:
                                light_inside += 1
                self.assertEqual(leaked, 0, 'unclipped shading leaked outside the projected atom')
                self.assertGreater(light_inside, 500, 'shading must not become a solid black blob')
                interior_ink[style, level] = dark_inside
        self.assertLess(interior_ink['none', '16'], 5)
        # Quantization changes intermediate coverage: do not compare whole-image
        # 4/64 ink totals. Every level must still produce actual interior Qt ink.
        for style, level in cases[1:]:
            self.assertGreater(interior_ink[style, level], interior_ink['none', '16'] + 100,
                               '%s/%s shading disappeared in the actual Qt raster' % (style, level))

    def test_qt_halftone_shared_coverage_plateau_has_no_level_count_drift(self):
        # Upstream 7b93 halftone-levels-browser-test.js fixture, measured in Qt
        # after the adapter's qtSvg conversion (including its mask handling).
        # Only the central constant-coverage plateau is shared across levels;
        # contours outside it intentionally differ. Whole-image ink need not match.
        self.render()
        self.runtime.run('''
            globalThis.originalMoleculeRender = MolEngraver.render;
            MolEngraver.render = function(molecule, options) {
                const width = options.width, height = options.height, scale = options.scale;
                const coverage = options.shadingBrightness;
                const scene = [{kind:'sphere', c:[0,0,0], r:1}];
                const project = p => [width/2+p[0]*scale, height/2-p[1]*scale];
                const illumination = (_n,p) => {
                    const t = Math.sign(p[0])*Math.max(0,(Math.abs(p[0])-.35)/.65);
                    return 1-2*Math.max(0,Math.min(1,coverage+t));
                };
                const body = MolDots.buildDots(scene, MolEngraver.depthAt, project,
                    scale, illumination, {width, height, quality:'preview',
                    shadingMode:'halftone', dotSpacing:7.5*options.textureScale,
                    dotSize:1.5*options.textureScale, dotContrast:1,
                    shadingLevels:options.shadingLevels, quantizeShading:true});
                // Model the precise owner's opaque paper, not just its ink.
                const paper = '<circle data-role="surface-fill" cx="'+width/2+
                    '" cy="'+height/2+'" r="'+scale+'" fill="white"/>';
                return '<svg xmlns="http://www.w3.org/2000/svg" width="'+width+
                    '" height="'+height+'" viewBox="0 0 '+width+' '+height+'">'+paper+body+'</svg>';
            };
        ''')
        rows = []
        try:
            for coverage in (.25, .5, .75, 1):
                for texture_scale in (.2, 1, 2.5):
                    with self.subTest(coverage=coverage, texture_scale=texture_scale):
                        samples = []
                        for level in ('4', '8', '16', '32', '64'):
                            reply, _ = self.render({
                                'model': 'xyz', 'xyz': '1\ncoverage plateau\nC 0 0 0\n',
                                'scale': 75, 'atomRadiusScale': 1 / .76,
                                'labels': False, 'colored': False, 'shading': 'halftone',
                                'shadingLevels': level, 'shadingBrightness': coverage,
                                'textureScale': texture_scale})
                            self.assertNotIn('error', reply)
                            renderer = qt.QSvgRenderer(qt.QByteArray(reply['svg'].encode()))
                            self.assertTrue(renderer.isValid())
                            view = renderer.viewBoxF()
                            root = ET.fromstring(reply['svg'])
                            width = math.ceil(float(root.get('width')))
                            height = math.ceil(float(root.get('height')))
                            self.assertAlmostEqual(view.width(), view.height(), places=6)
                            image = qt.QImage(width, height, qt.QImage.Format.Format_ARGB32)
                            image.fill(qt.Qt.GlobalColor.white)
                            painter = qt.QPainter(image)
                            renderer.render(painter, qt.QRectF(0, 0, width, height))
                            painter.end()
                            # Map the natural SVG center/32-unit ROI through the
                            # ceil-sized raster; don't assume a 256px viewport.
                            sx, sy = width / view.width(), height / view.height()
                            cx = (view.center().x() - view.left()) * sx
                            cy = (view.center().y() - view.top()) * sy
                            pixels = [image.pixelColor(x, y)
                                      for y in range(math.ceil(cy - 16 * sy - .5),
                                                     math.ceil(cy + 16 * sy - .5))
                                      for x in range(math.ceil(cx - 16 * sx - .5),
                                                     math.ceil(cx + 16 * sx - .5))]
                            self.assertGreaterEqual(len(pixels), 32 * 32)
                            ink = sum((765 - c.red() - c.green() - c.blue()) / (3 * 233)
                                      for c in pixels) / len(pixels)
                            self.assertGreater(ink, .01, 'Qt dropped the plateau texture')
                            samples.append(ink)
                        drift = max(samples) - min(samples)
                        rows.append({'coverage': coverage, 'textureScale': texture_scale,
                                     'samples': samples, 'drift': drift})
                        self.assertLessEqual(drift, .003, rows[-1])
        finally:
            self.runtime.run('MolEngraver.render = originalMoleculeRender;')
            print('Qt halftone plateau measurements: ' + json.dumps(rows))

    def test_colored_water_stipple_has_more_black_ink_than_flat_fill(self):
        counts = {}
        for style in ('none', 'stipple'):
            reply, _ = self.render({'model': 'water', 'scale': 36, 'shading': style,
                                    'colored': True, 'labels': False})
            _, image = self.valid_svg(reply)
            counts[style] = sum(
                image.pixelColor(x, y).alpha() > 128 and
                max(image.pixelColor(x, y).red(), image.pixelColor(x, y).green(),
                    image.pixelColor(x, y).blue()) < 100
                for y in range(image.height()) for x in range(image.width()))
        self.assertGreater(counts['stipple'], counts['none'] + 50,
                           'stipple SVG may exist while Qt silently drops every zero-length dash')

    def test_xyz_scientific_numbers_and_strict_invalid_sources(self):
        valid = '3\nscientific coords\nO 0e0 +0.0 -0.0\nH 9.572e-1 0 0\nH -2.39987E-1 .927297 0\n'
        self.valid_svg(self.render({'model': 'xyz', 'xyz': valid})[0])
        self.valid_svg(self.render({'model': 'xyz', 'xyz': '\ufeff' + valid.replace('\n', '\r\n')})[0])
        invalid = ['not xyz', '2\nmissing\nO 0 0 0\n',
                   '1\nunknown\nXx 0 0 0\n', '1\nnonfinite\nO NaN 0 0\n',
                   '1\ninfinity\nO 1e999 0 0\n', '1\nshort\nO 0 0\n',
                   '1\nextra\nO 0 0 0 extra\n', WATER + WATER,
                   '0\nempty\n', '97\nlarge\n' + 'H 0 0 0\n' * 97,
                   '1\n' + 'x' * 65536 + '\nO 0 0 0\n']
        for source in invalid:
            with self.subTest(source=source[:40]):
                self.assertIn('error', self.first(self.request({'model': 'xyz', 'xyz': source})))
        self.valid_svg(self.render({'model': 'xyz', 'xyz': WATER})[0])
        dense = '27\nbond budget\n' + ''.join(
            'C %s %s %s\n' % (x / 2, y / 2, z / 2)
            for x in range(3) for y in range(3) for z in range(3))
        self.assertIn('error', self.first(self.request({'model': 'xyz', 'xyz': dense})))
        self.assertIn('error', self.first(self.request({'model': 'xyz', 'xyz': '2\nhuge\nH 0 0 0\nH 100000 0 0\n'})))

    def test_rotation_source_style_and_color_do_not_reuse_wrong_cache(self):
        props = {'model': 'xyz', 'xyz': WATER}
        base, _ = self.render(props)
        self.assertEqual(self.render(props)[0], base)
        for changes in ({'yaw': 77}, {'pitch': 49}, {'roll': 91}, {'atomRadiusScale': 1.4},
                        {'xyz': WATER.replace('0.9572', '1.5')}, {'colored': False}):
            with self.subTest(changes=changes):
                changed, _ = self.render(dict(props, **changes))
                self.valid_svg(changed)
                self.assertNotEqual(changed['svg'], base['svg'])
        self.assertEqual(self.render(props)[0], base)
        mono, _ = self.render(dict(props, colored=False))
        _, image = self.valid_svg(mono)
        self.assertEqual(image_stats(image)[1], 0)
        different, _ = self.render(dict(props, colored=False), color='#246824')
        self.assertEqual(different['svg'], mono['svg'], 'root color is for labels only')

    def test_labels_use_qt_paths_and_font_color_cache(self):
        props = {'labels': True}
        req = self.request(props)
        first = self.first(req)
        self.assertIn('measure', first)
        measured = engine.measure_text_runs(qt, first['measure'], qt.QFont('Arial', 12))
        req['measured'] = measured
        reply = self.call(req)
        root, _ = self.valid_svg(reply)
        paths = [node for node in root.iter(SVG + 'path')]
        outline_paths = {run['path'] for run in measured.values() if run.get('path')}
        self.assertTrue(outline_paths)
        for outline in outline_paths:
            matches = [node for node in paths if node.get('d') == outline]
            self.assertGreaterEqual(len(matches), 2, 'measured Qt glyph needs halo and fill paths')
            self.assertEqual(matches[0].get('fill'), 'none')
            self.assertIn(matches[0].get('stroke', '').lower(), ('white', '#fff', '#ffffff'))
            self.assertEqual(matches[1].get('stroke'), 'none')
            self.assertEqual(matches[1].get('fill', '').lower(), '#123456')
        label = qt.QFont('Courier New', 12)
        changed, asked = self.render(props, label=label)
        self.assertTrue(asked)
        self.assertNotEqual(changed['svg'], reply['svg'])
        again, asked = self.render(props, label=label)
        self.assertFalse(asked)
        self.assertEqual(again, changed)
        colored, _ = self.render(props, color='#246824')
        self.assertNotEqual(colored['svg'], reply['svg'])

    def test_default_atom_radius_is_three_quarters_with_explicit_override(self):
        # Preserve the fast renderer's exact circle-radius contract separately.
        props = {'renderMode': 'fast', 'model': 'xyz',
                 'xyz': '1\ncarbon radius\nC 0 0 0\n', 'shading': 'none'}
        radii = []
        for overrides, expected in [({}, .75), ({'atomRadiusScale': 1}, 1)]:
            reply, _ = self.render(dict(props, **overrides))
            root = ET.fromstring(reply['svg'])
            circles = [node for node in root.iter(SVG + 'circle')
                       if node.get('data-role') == 'surface-fill']
            self.assertEqual(len(circles), 1)
            radius = float(circles[0].get('r'))
            self.assertAlmostEqual(radius, .76 * expected * 18 / .75, places=6)
            radii.append(radius)
        self.assertAlmostEqual(radii[0] / radii[1], .75, places=6)

    def test_hydrogen_label_toggle_preserves_atoms_bonds_and_cache_isolation(self):
        # Fast layers expose all atom circles and explicit bond masks.
        props = {'renderMode': 'fast', 'model': 'xyz', 'xyz': WATER,
                 'labels': True, 'shading': 'none'}
        shown, asked = self.render(props)
        self.assertEqual({run['text'] for run in asked}, {'O', 'H'})
        hidden, asked = self.render(dict(props, labelHydrogens=False))
        self.assertEqual({run['text'] for run in asked}, {'O'})
        for reply, label_ids in [(shown, {'0', '1', '2'}), (hidden, {'0'})]:
            root = ET.fromstring(reply['svg'])
            groups = list(root.iter(SVG + 'g'))
            labels = {node.get('data-surface-id') for node in groups
                      if node.get('data-role') == 'element-label'}
            self.assertEqual(labels, label_ids)
            atoms = [node for node in groups if node.get('data-role') == 'surface-layer'
                     and node.get('data-atom-id') is not None]
            self.assertEqual({node.get('data-atom-id') for node in atoms}, {'0', '1', '2'})
            self.assertTrue(all(any(child.tag == SVG + 'circle'
                                   and child.get('data-role') == 'surface-fill' for child in atom)
                                for atom in atoms))
            bonds = [node for node in groups if node.get('data-role') == 'bond-layer']
            self.assertEqual(len(bonds), 2)
            self.assertTrue(all(node.get('data-mask-empty') == 'false' for node in bonds))
        for values, expected in [(props, shown), (dict(props, labelHydrogens=False), hidden)]:
            cached, asked = self.render(values)
            self.assertFalse(asked)
            self.assertEqual(cached, expected)

    def test_all_hydrogen_hidden_labels_skip_measurement_and_label_padding(self):
        props = {'renderMode': 'fast', 'model': 'xyz',
                 'xyz': '2\nhydrogen\nH -.37 0 0\nH .37 0 0\n',
                 'labels': True, 'labelHydrogens': False, 'shading': 'none'}
        hidden, asked = self.render(props)
        self.assertFalse(asked)
        root, _ = self.valid_svg(hidden)
        self.assertFalse([node for node in root.iter(SVG + 'g')
                          if node.get('data-role') == 'element-label'])
        self.assertEqual(sum(node.get('data-role') == 'surface-fill'
                             for node in root.iter(SVG + 'circle')), 2)
        plain, asked = self.render(dict(props, labels=False))
        self.assertFalse(asked)
        for dimension in ('width', 'height'):
            self.assertAlmostEqual(hidden[dimension], plain[dimension], places=7)
        shown, asked = self.render(dict(props, labelHydrogens=True))
        self.assertEqual({run['text'] for run in asked}, {'H'})
        self.valid_svg(shown)
        self.assertGreater(shown['width'], hidden['width'])

    def test_label_ink_centers_match_projected_atoms_in_both_axes(self):
        cases = []
        for family in ('Arial', 'Times New Roman'):
            for element in ('C', 'H', 'O', 'Cl'):
                for size in (6, 12, 24):
                    cases.append((family, False, size, [element],
                                  '1\ncentered label\n' + element + ' 0 0 0\n'))
            for size in (6, 12, 24):
                cases.append((family, False, size, ['O', 'H', 'H'], WATER))
        # Italic Al has different bearings from advance-width centering; signed
        # bearings must survive, rather than clamping ink.x to zero.
        cases.append(('Times New Roman', True, 24, ['Al'], '1\nitalic\nAl 0 0 0\n'))
        for family, italic, size, elements, xyz in cases:
            with self.subTest(family=family, italic=italic, size=size, elements=elements):
                label = qt.QFont(family, 12)
                label.setItalic(italic)
                # Exact projected centers are obtained from fast surface circles;
                # precise visibility can correctly omit an occluded atom label.
                req = self.request({'renderMode': 'fast', 'model': 'xyz', 'xyz': xyz, 'labels': True,
                                    'shading': 'none', 'labelSize': size,
                                    'pitch': 35, 'yaw': 77, 'roll': 23}, label=label)
                first = self.first(req)
                self.assertIn('measure', first)
                measured = engine.measure_text_runs(qt, first['measure'], label)
                # Independently obtain visible ink from Qt, not from advance
                # width, h/d, or the new host 'ink' payload under test.
                canonical = qt.QFont(label)
                canonical.setPixelSize(1000)
                canonical.setStyleStrategy(qt.QFont.StyleStrategy.PreferOutline)
                canonical.setHintingPreference(qt.QFont.HintingPreference.PreferNoHinting)
                boxes = {}
                for element in set(elements):
                    path = qt.QPainterPath()
                    path.addText(qt.QPointF(0, 0), canonical, element)
                    boxes[element] = box = path.boundingRect()
                    ink = measured[element]['ink']
                    for key, value in [('x', box.x()), ('y', box.y()),
                                       ('w', box.width()), ('h', box.height())]:
                        self.assertAlmostEqual(ink[key], value / 1000, places=6)
                req['measured'] = measured
                reply = self.call(req)
                self.assertNotIn('error', reply)
                root = ET.fromstring(reply['svg'])
                surfaces = {node.get('data-surface-id'): node
                            for node in root.iter(SVG + 'g')
                            if node.get('data-role') == 'surface-layer'
                            and node.get('data-atom-id') is not None}
                labels = [node for node in root.iter(SVG + 'g')
                          if node.get('data-role') == 'element-label']
                self.assertEqual(len(labels), len(elements))
                for group in labels:
                    atom_id = group.get('data-surface-id')
                    surface = surfaces[atom_id]
                    circle = next(node for node in surface
                                  if node.tag == SVG + 'circle' and node.get('data-role') == 'surface-fill')
                    transform = re.fullmatch(r'translate\(([^ ]+) ([^)]+)\) scale\(([^)]+)\)',
                                             group.get('transform', ''))
                    self.assertIsNotNone(transform)
                    tx, ty, scale = map(float, transform.groups())
                    self.assertAlmostEqual(scale, size / .75 / 1000, places=9)
                    element = elements[int(atom_id)]
                    box = boxes[element]
                    paths = list(group.iter(SVG + 'path'))
                    self.assertEqual(paths[-1].get('d'), measured[element]['path'])
                    self.assertAlmostEqual(tx + box.center().x() * scale,
                                           float(circle.get('cx')), places=5)
                    self.assertAlmostEqual(ty + box.center().y() * scale,
                                           float(circle.get('cy')), places=5)

    def test_scale_points_per_angstrom_and_native_page_dpi_independence(self):
        small, _ = self.render({'scale': 18})
        large, _ = self.render({'scale': 36})
        for dimension in ('width', 'height'):
            # Natural geometry scales in pt/angstrom; the two 12px safety
            # margins retain their physical size (24px * .75pt/px = 18pt).
            self.assertAlmostEqual(large[dimension] - 18, (small[dimension] - 18) * 2, places=6)
        base_image, helper = self.painted()
        self.assertGreater(image_stats(base_image)[0], 20, 'default water must draw even when xyz is empty')
        base_dims = helper.getControlGraph(self.widget)[0].dims
        base_box = image_stats(base_image)[2]
        for pagesize, dpi, factor in [((1000, 600), 96, 1), ((1000, 600), 192, 2)]:
            image, helper = self.painted(pagesize, dpi)
            dims = helper.getControlGraph(self.widget)[0].dims
            for dimension in (0, 1):
                self.assertAlmostEqual(dims[dimension], base_dims[dimension] * factor, places=6)
                self.assertAlmostEqual(image_stats(image)[2][dimension], base_box[dimension] * factor, delta=2)

    def test_visible_nonfatal_errors_recover_and_native_controls(self):
        self.settings.get('model').set('xyz')
        for source, error in [('bad XYZ', True), (WATER, False)]:
            self.settings.get('xyz').set(source)
            with patch.object(self.platform.state, 'note') as note:
                image, helper = self.painted()
                self.assertEqual(note.called, error, note.call_args_list)
            self.assertGreater(image_stats(image)[0], 20)
        controls = helper.getControlGraph(self.widget)
        self.assertEqual(len(controls), 1)
        control = controls[0]
        item = control.createGraphicsItem(None)
        self.assertTrue(all(not corner.isVisible() for corner in item.corners))
        self.assertIsNotNone(item.rotator)
        before = {name: list(getattr(self.settings, name)) for name in ('xPos', 'yPos', 'rotate')}
        control.posn = [150, 210]
        control.angle = 37
        self.widget.updateControlItem(control)
        for name, value in [('xPos', .3), ('yPos', .3), ('rotate', 37)]:
            self.assertAlmostEqual(getattr(self.settings, name)[0], value)
        self.doc.undoOperation()
        for name, value in before.items():
            self.assertEqual(list(getattr(self.settings, name)), value)

    def test_real_insert_menu_and_native_undo(self):
        fake = copy.copy(veusz.setting.settingdb)
        fake.database = dict(veusz.setting.settingdb.database)
        interface = veusz.document.CommandInterface
        names = interface.safe_commands + interface.import_commands
        missing = {name for name in names if not hasattr(interface, name)}
        self.assertLessEqual(missing, {'ImportFITSFile'})
        APP.clipboard().setMimeData(qt.QMimeData())
        with patch.object(qt, 'QSettings', MemoryQSettings), \
             patch.object(veusz.setting, 'settingdb', fake), \
             patch.object(interface, 'safe_commands', [n for n in interface.safe_commands if n not in missing]), \
             patch.object(interface, 'import_commands', [n for n in interface.import_commands if n not in missing]):
            window = veusz.windows.mainwindow.MainWindow()
            try:
                commands = veusz.document.CommandInterface(window.document)
                page_name = commands.Add('page')
                page = window.document.resolveWidgetPath(None, '/' + page_name)
                window.treeedit.selectWidget(page)
                action = window.treeedit.vzactions['add.molecule3d']
                self.assertIn(action, window.menus['insert'].actions())
                self.assertTrue(action.isEnabled())
                count = len(page.children)
                action.trigger()
                self.assertEqual(len(page.children), count + 1)
                self.assertEqual(page.children[-1].typename, 'molecule3d')
                self.assertEqual(page.children[-1].settings.model, 'water')
                window.document.undoOperation()
                self.assertEqual(len(page.children), count)
                window.document.redoOperation()
                self.assertEqual(page.children[-1].typename, 'molecule3d')
            finally:
                window.document.setModified(False)
                window.close()
                window.deleteLater()
                APP.processEvents()

    def test_checked_in_six_widget_example_loads_and_exports(self):
        doc = veusz.document.Document()
        interface = veusz.document.CommandInterface
        missing = {name for name in interface.safe_commands if not hasattr(interface, name)}
        self.assertLessEqual(missing, {'ImportFITSFile'})
        with patch.object(interface, 'safe_commands', [n for n in interface.safe_commands if n not in missing]):
            doc.load(str(FEATURE / 'examples' / 'molecules.vsz'))
        page = doc.resolveWidgetPath(None, '/molecules3d')
        molecules = {w.name: w for w in page.children if w.typename == 'molecule3d'}
        self.assertEqual(set(molecules), {'water', 'ethanol', 'c60', 'halftone', 'textures', 'xyz'})
        self.assertTrue(molecules['water'].settings.labels)
        self.assertEqual(molecules['ethanol'].settings.shading, 'stipple')
        self.assertEqual(molecules['halftone'].settings.shading, 'halftone')
        self.assertTrue(molecules['textures'].settings.elementTextures)
        self.assertIn('Carbon dioxide', molecules['xyz'].settings.xyz)
        commands = interface(doc)
        with patch.object(self.platform.state, 'note') as note, \
             patch.object(self.feature, 'render', wraps=self.feature.render) as render:
            for extension in ('png', 'svg'):
                output = OUT / ('six-widget-example.' + extension)
                commands.Export(str(output), dpi=96)
                self.assertTrue(output.is_file())
                if extension == 'png':
                    image = qt.QImage(str(output))
                    self.assertGreater(image_stats(image)[0], 1000)
                    # Check molecule areas only, excluding the caption rows.
                    for x, y in ((.18, .24), (.50, .24), (.82, .24),
                                 (.18, .69), (.50, .69), (.82, .69)):
                        rect = qt.QRect(int((x-.09)*image.width()), int((y-.09)*image.height()),
                                        int(.18*image.width()), int(.18*image.height()))
                        self.assertGreater(image_stats(image.copy(rect))[0], 20)
                else:
                    root = ET.parse(output).getroot()
                    self.assertTrue(list(root.iter(SVG + 'path')))
                    # Qt may embed raster tiles for masks, clipping or patterns;
                    # source SVG geometry is tested separately from native export.
                    self.assertTrue(qt.QSvgRenderer(str(output)).isValid())
            self.assertGreaterEqual(render.call_count, 12)
            note.assert_not_called()

    def test_real_document_embeds_xyz_roundtrip_and_png_svg_export(self):
        self.commands.Set('width', '10cm')
        self.commands.Set('height', '6cm')
        for name, value in [('model', 'xyz'), ('xyz', WATER), ('scale', 22),
                            ('yaw', 43), ('labels', True), ('labelHydrogens', False),
                            ('atomRadiusScale', 1), ('font', 'Arial'),
                            ('shadingLevels', '32'), ('shadingBrightness', -.25),
                            ('shadingContrast', 1.75), ('renderMode', 'fast'),
                            ('castShadows', True), ('shadowStrength', .45)]:
            self.commands.Set('molecule/' + name, value)
        self.commands.Add('graph', name='graph')
        self.commands.To('graph')
        self.commands.Add('molecule3d', name='in_graph')
        self.commands.Set('in_graph/hide', True)
        child = self.doc.resolveWidgetPath(None, '/' + self.page + '/graph/in_graph')
        self.assertEqual(child.parent.typename, 'graph')
        self.assertEqual(self.widget.parent.typename, 'page')
        self.commands.To('/' + self.page)
        self.commands.Set('graph/hide', True)
        for extension in ('png', 'svg'):
            output = OUT / ('embedded-water.' + extension)
            self.commands.Export(str(output), dpi=96)
            self.assertTrue(output.is_file())
            if extension == 'png':
                self.assertGreater(image_stats(qt.QImage(str(output)))[0], 20)
            else:
                root = ET.parse(output).getroot()
                self.assertTrue(list(root.iter(SVG + 'path')))
                self.assertFalse(list(root.iter(SVG + 'text')))
                # Native Qt export can rasterize clipping/masks/pattern tiles;
                # Source SVG permits only vector geometry and embedded PNG stipple
                # tiles; the native exporter may rasterize additional Qt layers.
        saved = OUT / 'molecule3d-roundtrip.vsz'
        self.commands.Save(str(saved))
        contents = saved.read_text(encoding='utf-8')
        self.assertIn("Add('molecule3d'", contents)
        self.assertIn('Embedded water', contents)
        self.assertNotIn('Text/molecule3d', contents)
        restored = veusz.document.Document()
        interface = veusz.document.CommandInterface
        missing = {name for name in interface.safe_commands if not hasattr(interface, name)}
        self.assertLessEqual(missing, {'ImportFITSFile'})
        with patch.object(interface, 'safe_commands', [n for n in interface.safe_commands if n not in missing]):
            restored.load(str(saved))
        settings = restored.resolveWidgetPath(None, '/' + self.page + '/molecule').settings
        self.assertEqual(settings.xyz, WATER)
        self.assertEqual(settings.model, 'xyz')
        self.assertEqual(settings.scale, 22)
        self.assertEqual(settings.yaw, 43)
        self.assertTrue(settings.labels)
        self.assertFalse(settings.labelHydrogens)
        self.assertEqual(settings.atomRadiusScale, 1)
        self.assertEqual(settings.shadingLevels, '32')
        self.assertEqual(settings.shadingBrightness, -.25)
        self.assertEqual(settings.shadingContrast, 1.75)
        self.assertEqual(settings.renderMode, 'fast')
        self.assertTrue(settings.castShadows, 'fast must retain the saved shadow switch')
        self.assertEqual(settings.shadowStrength, .45)
        for name in ('shadingLevels', 'shadingBrightness', 'shadingContrast',
                     'renderMode', 'castShadows', 'shadowStrength'):
            self.assertIs(settings.get(name).parent, settings)
            self.assertIn("Set('%s'," % name, contents)
            for page in ('Appearance', 'View', 'Lighting'):
                self.assertNotIn(page + '/' + name, contents)
        self.assertNotIn('size', settings)


if __name__ == '__main__':
    unittest.main(verbosity=2)
