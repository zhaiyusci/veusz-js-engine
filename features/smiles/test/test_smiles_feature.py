"""Real QuickJS + Qt regressions, using only ../upstream-veusz.

Run: python features/smiles/test/test_smiles_feature.py
Outputs use inherited-ACL build-test-smiles, never a private temporary folder.
The parser examples test supported drawings, not chemical validation.
"""
import copy
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

class MemoryQSettings:
    """Keep even upstream's import-time preference accesses in memory."""
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
        # A fresh native registration per test keeps deferred bundles/cache cold.
        factory = veusz.document.thefactory
        registry = patch.dict(factory.regwidgets)
        registry.start()
        self.addCleanup(registry.stop)
        factory.regwidgets.pop('smiles', None)
        self.feature = engine.install_js_feature(self.platform, FEATURE / 'feature.js', FEATURE, 'smiles')
        self.runtime = self.feature.runtime
        self.addCleanup(self.platform.close_all)
        self.doc = veusz.document.Document()
        self.commands = veusz.document.CommandInterface(self.doc)
        self.page = self.commands.Add('page')
        self.commands.To(self.page)
        self.commands.Add('smiles', name='molecule')
        self.widget = self.doc.resolveWidgetPath(None, '/' + self.page + '/molecule')
        self.settings = self.widget.settings

    def request(self, text, size=12, colored=True, face=None, **extra):
        req = dict(text='NOT THE MOLECULE SOURCE', size=size, color='#123456',
                   props=dict(smiles=text, colored=colored),
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

    def draw(self, pagesize=(500, 300), dpi=100):
        helper = veusz.document.PaintHelper(self.doc, pagesize, dpi=(dpi, dpi))
        self.widget.draw([0, 0, *pagesize], helper)
        return helper

    def painted(self, pagesize=(500, 300), dpi=100):
        helper = self.draw(pagesize, dpi)
        image = qt.QImage(*pagesize, qt.QImage.Format.Format_ARGB32)
        image.fill(qt.Qt.GlobalColor.transparent)
        painter = qt.QPainter(image)
        helper.renderToPainter(painter)
        painter.end()
        return image, helper

    def test_declaration_native_settings_and_empty_hidden_stay_cold(self):
        declaration = json.loads(self.runtime.call('veuszDescribe', ''))
        self.assertEqual(declaration['target'], 'widget')
        self.assertEqual(declaration['source'], 'smiles')
        self.assertEqual(declaration['version'], '0.3.0')
        self.assertEqual(declaration['sizing'], 'font')
        self.assertEqual(self.settings.size, '12pt')
        self.assertEqual({p['name'] for p in declaration['properties']}, {'smiles', 'colored'})
        self.assertEqual(self.settings.smiles, 'CCO')
        self.assertTrue(self.settings.colored)
        for name in ('smiles', 'colored', 'font', 'size', 'color', 'xPos', 'yPos', 'rotate', 'hide'):
            self.assertIn(name, self.settings)
        for name in ('Text', 'on', 'scale', 'width', 'height', 'smilesColored', 'smilesScale'):
            self.assertNotIn(name, self.settings)
        text = veusz.setting.collections.Text('Text')
        for name in ('smiles', 'smilesColored', 'smilesScale'):
            self.assertNotIn(name, text)
        self.assertEqual(self.runtime.run('typeof globalThis.smilesToSvg'), 'undefined')
        with patch.object(self.runtime, 'eval_file', wraps=self.runtime.eval_file) as evaluate:
            for source in ('', ' \n\t '):
                self.assertIsNone(self.call(self.request(source)))
                self.settings.get('smiles').set(source)
                self.draw()
            self.settings.get('smiles').set('CCO')
            self.settings.get('hide').set(True)
            self.draw()
            evaluate.assert_not_called()
        self.assertFalse({Path(p).name for p in self.runtime.loaded_scripts} & {'headless.js', 'smiles-drawer.js'})

    def test_real_widget_loads_once_and_shapes_with_qt(self):
        with patch.object(self.runtime, 'eval_file', wraps=self.runtime.eval_file) as evaluate, \
             patch.object(engine, 'measure_text_runs', wraps=engine.measure_text_runs) as measure, \
             patch.object(self.feature, 'render', wraps=self.feature.render) as render:
            self.draw()
            self.assertEqual([Path(c.args[0]).name for c in evaluate.call_args_list], ['headless.js', 'smiles-drawer.js'])
            self.assertEqual(measure.call_count, 1)
            self.assertTrue(any('O' in r['text'] for r in measure.call_args.args[1]))
            self.assertEqual(render.call_args.args[0], 'CCO')
            self.assertAlmostEqual(render.call_args.args[1], 12.0, places=7)
            self.draw()
            self.assertEqual(measure.call_count, 1)
            self.assertEqual(evaluate.call_count, 2)

    def test_native_move_rotate_control_and_undo_without_resize(self):
        helper = self.draw()
        controls = helper.getControlGraph(self.widget)
        self.assertEqual(len(controls), 1)
        control = controls[0]
        item = control.createGraphicsItem(None)
        for corner in item.corners:
            self.assertFalse(corner.isVisible())
            self.assertFalse(corner.flags() & qt.QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self.assertEqual(corner.acceptedMouseButtons(), qt.Qt.MouseButton.NoButton)
        self.assertIsNotNone(item.rotator)
        self.assertTrue(item.rotator.isVisible())
        control.posn = [150, 210]
        control.angle = 37
        before = {name: list(getattr(self.settings, name))
                  for name in ('xPos', 'yPos', 'rotate')}
        self.widget.updateControlItem(control)
        self.assertEqual(self.settings.size, '12pt')
        for name, value in [('xPos', .3), ('yPos', .3), ('rotate', 37)]:
            self.assertAlmostEqual(getattr(self.settings, name)[0], value)
        self.doc.undoOperation()
        for name, value in before.items():
            self.assertEqual(list(getattr(self.settings, name)), value)

    def test_font_size_controls_natural_bounds_and_root_font_color(self):
        self.settings.get('font').set('Courier New')
        self.settings.get('color').set('#246824')
        self.settings.get('colored').set(False)
        self.settings.get('smiles').set('NCCO')
        boxes, bounds = [], []
        for size in (12, 24):
            self.settings.get('size').set(str(size) + 'pt')
            with patch.object(engine, 'measure_text_runs', wraps=engine.measure_text_runs) as measure, \
                 patch.object(self.feature, 'render', wraps=self.feature.render) as render:
                image, helper = self.painted()
                self.assertEqual(measure.call_args.args[2].family(), 'Courier New')
                self.assertAlmostEqual(measure.call_args.args[2].pointSizeF(), size, places=7)
                self.assertAlmostEqual(render.call_args.args[1], size, places=7)
                self.assertEqual(render.call_args.args[2], '#246824')
            ink, colored, box = image_stats(image)
            self.assertGreater(ink, 50)
            self.assertGreater(colored, 10)
            boxes.append(box)
            bounds.append(helper.getControlGraph(self.widget)[0].dims)
        for dimension in (0, 1):
            self.assertAlmostEqual(boxes[1][dimension], boxes[0][dimension] * 2, delta=2)
            self.assertAlmostEqual(bounds[1][dimension], bounds[0][dimension] * 2, places=6)

    def test_natural_geometry_is_page_independent_and_dpi_aware(self):
        base_image, base_helper = self.painted(dpi=96)
        base_box = image_stats(base_image)[2]
        base_bounds = base_helper.getControlGraph(self.widget)[0].dims
        for pagesize, dpi, factor in [((1000, 600), 96, 1), ((1000, 600), 192, 2)]:
            image, helper = self.painted(pagesize, dpi)
            box = image_stats(image)[2]
            bounds = helper.getControlGraph(self.widget)[0].dims
            for dimension in (0, 1):
                self.assertAlmostEqual(box[dimension], base_box[dimension] * factor, delta=2)
                self.assertAlmostEqual(bounds[dimension], base_bounds[dimension] * factor, places=6)

    def test_source_changes_update_natural_selection_bounds(self):
        self.settings.get('smiles').set('CCO')
        first = self.draw().getControlGraph(self.widget)[0].dims
        self.settings.get('smiles').set('CCCCCCO')
        changed = self.draw().getControlGraph(self.widget)[0].dims
        self.assertNotEqual(tuple(first), tuple(changed))
        self.settings.get('smiles').set('CCO')
        restored = self.draw().getControlGraph(self.widget)[0].dims
        self.assertEqual(tuple(first), tuple(restored))
        self.settings.get('smiles').set('')
        self.assertFalse(self.draw().getControlGraph(self.widget))

    def test_graph_parent_is_native_and_invalid_draw_is_visible_recoverable(self):
        self.commands.Add('graph', name='graph')
        self.commands.To('graph')
        self.commands.Add('smiles', name='graphmolecule')
        child = self.doc.resolveWidgetPath(None, '/' + self.page + '/graph/graphmolecule')
        self.assertEqual(child.parent.typename, 'graph')
        self.assertEqual(self.widget.parent.typename, 'page')
        for source, should_error in [('C1CC', True), ('CCO', False)]:
            with self.subTest(source=source):
                child.settings.get('smiles').set(source)
                image = qt.QImage(500, 300, qt.QImage.Format.Format_ARGB32)
                image.fill(qt.Qt.GlobalColor.transparent)
                painter = qt.QPainter(image)
                try:
                    with patch.object(self.platform.state, 'note') as note:
                        helper = veusz.document.PaintHelper(self.doc, (500, 300))
                        child.draw([10, 10, 490, 290], helper)
                        helper.renderToPainter(painter)
                        self.assertEqual(note.called, should_error, note.call_args_list)
                        if should_error:
                            self.assertIn('SMILES', note.call_args.args[0])
                finally:
                    painter.end()
                self.assertGreater(image_stats(image)[0], 50, 'invalid input must show a visible diagnostic')
        helper = veusz.document.PaintHelper(self.doc, (500, 300))
        child.draw([30, 20, 470, 280], helper)
        self.assertTrue(helper.getControlGraph(child))

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

    def test_point_size_scales_reply_and_is_part_of_cache_key(self):
        base, _ = self.render('NCCO', size=12)
        large, asked = self.render('NCCO', size=24)
        self.assertTrue(asked, 'size changes must not reuse the 12pt cached reply')
        for dimension in ('width', 'height'):
            self.assertAlmostEqual(large[dimension], base[dimension] * 2, places=7)
        cached, asked = self.render('NCCO', size=24)
        self.assertEqual(cached, large)
        self.assertFalse(asked)
        original, asked = self.render('NCCO', size=12)
        self.assertEqual(original, base)
        self.assertFalse(asked)
        for size in (0, -1, 'NaN', 'Infinity'):
            with self.subTest(size=size):
                self.assertIn('error', self.first(self.request('CCO', size=size)))

    def test_trim_and_font_face_cache(self):
        base, asked = self.render('CCO')
        self.assertTrue(asked)
        cached, asked = self.render('  CCO \n')
        self.assertEqual(cached, base)
        self.assertFalse(asked)
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
        fake = copy.copy(veusz.setting.settingdb)
        fake.database = dict(veusz.setting.settingdb.database)
        fake[engine.FEATURE_DISABLED_KEY] = []
        cls.qsettings_patch = patch.object(qt, 'QSettings', MemoryQSettings)
        cls.qsettings_patch.start()
        cls.addClassCleanup(cls.qsettings_patch.stop)
        cls.preference_patch = patch.object(veusz.setting, 'settingdb', fake)
        cls.preference_patch.start()
        cls.addClassCleanup(cls.preference_patch.stop)
        cls.platform = engine.install(verbose=False)
        cls.feature = next(f for f in cls.platform.feature_objects() if f.name == 'smiles')
        OUT.mkdir(exist_ok=True)

    def test_real_insert_menu_page_graph_and_undo(self):
        interface = veusz.document.CommandInterface
        names = interface.import_commands + interface.safe_commands
        missing = {name for name in names if not hasattr(interface, name)}
        self.assertLessEqual(missing, {'ImportFITSFile'})
        imports = [name for name in interface.import_commands if name not in missing]
        safe = [name for name in interface.safe_commands if name not in missing]
        APP.clipboard().setMimeData(qt.QMimeData())
        with patch.object(interface, 'import_commands', imports), \
             patch.object(interface, 'safe_commands', safe):
            window = veusz.windows.mainwindow.MainWindow()
        try:
            commands = veusz.document.CommandInterface(window.document)
            page_name = commands.Add('page')
            commands.To(page_name)
            commands.Add('graph', name='graph')
            page = window.document.resolveWidgetPath(None, '/' + page_name)
            graph = window.document.resolveWidgetPath(None, '/' + page_name + '/graph')
            action = window.treeedit.vzactions['add.smiles']
            self.assertIn(action, window.menus['insert'].actions())
            self.assertEqual(sum(a is action for a in window.menus['insert'].actions()), 1)
            for parent in (page, graph):
                window.treeedit.selectWidget(parent)
                self.assertTrue(action.isEnabled())
                before = len(parent.children)
                action.trigger()
                self.assertEqual(len(parent.children), before + 1)
                molecule = parent.children[-1]
                self.assertEqual(molecule.typename, 'smiles')
                self.assertEqual(molecule.settings.smiles, 'CCO')
                window.document.undoOperation()
                self.assertEqual(len(parent.children), before)
                window.document.redoOperation()
                self.assertEqual(parent.children[-1].typename, 'smiles')
        finally:
            # Avoid modified-document dialogs; all QSettings persistence is fake.
            window.document.setModified(False)
            window.close()
            window.deleteLater()
            APP.processEvents()

    def test_export_dpi_doubles_pixels_not_point_geometry(self):
        doc = veusz.document.Document()
        commands = veusz.document.CommandInterface(doc)
        page = commands.Add('page')
        commands.To(page)
        commands.Set('width', '10cm')
        commands.Set('height', '6cm')
        commands.Add('smiles', name='molecule')
        commands.Set('molecule/smiles', 'NCCO')
        boxes = []
        replies = []
        for dpi in (96, 192):
            path = OUT / ('font-sized-' + str(dpi) + '.png')
            with patch.object(self.feature, 'render', wraps=self.feature.render) as render:
                commands.Export(str(path), dpi=dpi)
                self.assertTrue(render.called)
                self.assertAlmostEqual(render.call_args.args[1], 12.0, places=7)
                args, kwargs = render.call_args
                replies.append(json.loads(self.feature.render(*args, **kwargs)))
            boxes.append(image_stats(qt.QImage(str(path)))[2])
        for dimension in (0, 1):
            self.assertAlmostEqual(boxes[1][dimension], boxes[0][dimension] * 2, delta=2)
        for dimension in ('width', 'height'):
            self.assertAlmostEqual(replies[0][dimension], replies[1][dimension], places=7)

    def test_real_page_png_svg_and_document_roundtrip(self):
        doc = veusz.document.Document()
        commands = veusz.document.CommandInterface(doc)
        page = commands.Add('page')
        commands.To(page)
        commands.Set('width', '10cm')
        commands.Set('height', '6cm')
        commands.Add('smiles', name='molecule')
        commands.Set('molecule/smiles', '[13CH3][NH3+]')
        commands.Set('molecule/font', 'Arial')
        commands.Set('molecule/color', 'black')
        commands.Set('molecule/size', '24pt')
        commands.Set('molecule/rotate', [17])
        commands.Set('molecule/colored', True)
        outputs = {}
        with patch.object(self.feature, 'render', wraps=self.feature.render) as render:
            for mode in (True, False):
                commands.Set('molecule/colored', mode)
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
        self.assertIn("Add('smiles'", contents)
        for name in ('smiles', 'colored', 'size', 'rotate'):
            self.assertIn(name, contents)
        for name in ('Text/smiles', 'smilesColored', 'smilesScale'):
            self.assertNotIn(name, contents)
        restored = veusz.document.Document()
        # Upstream advertises optional FITS import commands even when astropy
        # is absent. Exclude only uninstalled commands; execute its real loader.
        interface = veusz.document.CommandInterface
        missing = {name for name in interface.safe_commands if not hasattr(interface, name)}
        self.assertLessEqual(missing, {'ImportFITSFile'})
        available = [name for name in interface.safe_commands if name not in missing]
        with patch.object(interface, 'safe_commands', available):
            restored.load(str(saved))
        widget = restored.resolveWidgetPath(None, '/' + page + '/molecule')
        self.assertEqual(widget.typename, 'smiles')
        settings = widget.settings
        self.assertEqual(settings.smiles, '[13CH3][NH3+]')
        self.assertFalse(settings.colored)
        self.assertEqual(settings.size, '24pt')
        self.assertNotIn('width', settings)
        self.assertNotIn('height', settings)
        self.assertEqual(settings.rotate, [17])
        self.assertEqual(settings.font, 'Arial')


if __name__ == '__main__':
    unittest.main(verbosity=2)
