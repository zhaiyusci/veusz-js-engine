"""Lazy bundle regressions: python test/test_lazy_bundles.py (Veusz on PYTHONPATH)."""
import json
import os
from pathlib import Path
import sys
import shutil
from contextlib import contextmanager
from uuid import uuid4
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
os.environ['VEUSZ_JS_ENGINE_DEFER'] = '1'
if sys.platform != 'win32':
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(PROJECT))
import veusz_js_engine as engine


@contextmanager
def fixture_directory():
    # Ordinary inherited permissions also work with Windows sandbox tokens;
    # Python 3.14 TemporaryDirectory's private ACL can exclude those tokens.
    directory = PROJECT / ('build-test-lazy-' + uuid4().hex)
    directory.mkdir()
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


class DeclarationTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(fixture_directory())
        self.entry = self.directory / 'feature.js'
        self.bundle = self.directory / 'bundle.js'
        self.bundle.write_text('globalThis.loaded = true;', encoding='utf-8')
        (self.directory / 'helper.js').write_text('', encoding='utf-8')

    def test_only_first_line_opt_in_defers_named_sibling(self):
        for header, deferred in [('', False),
                                 ('// comment\n// VEUSZ-DEFER ["bundle.js"]\n', False),
                                 ('// VEUSZ-DEFER ["bundle.js"]\n', True)]:
            with self.subTest(header=header):
                self.entry.write_text(header + '// entry\n', encoding='utf-8')
                order = engine._js_load_order(self.entry, self.directory)
                self.assertEqual(self.bundle in order, not deferred)
                self.assertIn(self.directory / 'helper.js', order)
                self.assertEqual(order[-1], self.entry)
                self.assertEqual(engine._deferred_bundles(self.entry, self.directory),
                                 {self.bundle.resolve()} if deferred else set())
                self.assertEqual(engine._js_load_order(self.entry, None), [self.entry])

    def test_windows_case_alias_cannot_defer_the_entry(self):
        if sys.platform != 'win32':
            self.skipTest('case-insensitive Windows path alias')
        self.entry.write_text('// VEUSZ-DEFER ["FEATURE.JS"]\n', encoding='utf-8')
        with self.assertRaises(engine.JsEngineError):
            engine._deferred_bundles(self.entry, self.directory)

    def test_malformed_and_escaping_declarations_are_rejected(self):
        for value in ['not json', '{}', '"bundle.js"', '[1]', '[null]',
                      '["../bundle.js"]', '["fonts/bundle.js"]',
                      '["..\\\\bundle.js"]', '["C:bundle.js"]',
                      '["bundle.txt"]', '["feature.js"]',
                      json.dumps([engine.JS_API_FILE])]:
            with self.subTest(value=value):
                self.entry.write_text('// VEUSZ-DEFER ' + value + '\n', encoding='utf-8')
                with self.assertRaises(engine.JsEngineError):
                    engine._js_load_order(self.entry, self.directory)

    def test_load_allowlist_and_font_compatibility(self):
        fonts = self.directory / 'fonts'
        fonts.mkdir()
        font = fonts / 'extra.js'
        font.write_text('globalThis.fontLoaded = true;', encoding='utf-8')
        runtime = SimpleNamespace(deferred_bundles={self.bundle.resolve()},
                                  loaded_scripts=set(), eval_file=lambda p: evaluated.append(p))
        evaluated = []
        feature = SimpleNamespace(name='fixture', feature_dir=self.directory,
                                  entry=self.entry, runtime=runtime)
        for name in ['bundle.js', './bundle.js', 'fonts/extra.js', 'fonts/extra.js']:
            engine.load_feature_file(feature, name)
        self.assertEqual(evaluated, [self.bundle.resolve(), font.resolve()])
        for name in ['helper.js', 'feature.js', '../bundle.js', 'fonts/../helper.js',
                     str(PROJECT / 'veusz_js_engine.py'), 'fonts/missing.js']:
            with self.subTest(name=name), self.assertRaises(engine.JsEngineError):
                engine.load_feature_file(feature, name)
        self.assertEqual(len(evaluated), 2)


class InstalledBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import veusz.qtall as qt
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def install(self, directory):
        platform = engine.Platform(PROJECT)
        hooks, settings = [], {}
        # Keep installation real, but isolate global Veusz hooks/settings and
        # return the final reply instead of constructing a painter-backed item.
        with patch.object(platform, 'add_setting',
                          side_effect=lambda target, parent, setting: settings.update({setting.name: setting})), \
             patch.object(platform, 'hook_draw', side_effect=lambda target, hook: hooks.append(hook)), \
             patch.object(platform, '_svg_renderer_class',
                          return_value=lambda *args, **kwargs: kwargs['reply']):
            feature = engine.install_js_feature(platform, directory / 'feature.js',
                                                directory, directory.name)
        self.addCleanup(feature.runtime.close)
        platform.state.native_renderer = lambda painter, font, x, y, text, **kw: {'delegate': text}

        def draw(text='x', **props):
            for prop in feature.properties:
                if prop['name'] in props:
                    settings[feature.setting_name(prop)].val = props[prop['name']]
            with patch.object(engine, '_font_size_pt', return_value=20), \
                 patch.object(engine, '_pen_color', return_value=None), \
                 patch.object(engine, 'text_font_key', return_value=''):
                return hooks[0](None, None, 0, 0, text, settings)
        return platform, feature, settings, draw

    def test_real_features_stay_cold_then_load_once(self):
        for name, bundle, symbol, output in [
                ('mathjax', 'mathjax.js', '__veuszMathjax', 'svg'),
                ('katex', 'katex.min.js', 'katex', 'delegate')]:
            with self.subTest(feature=name):
                directory = PROJECT / 'features' / name
                platform, feature, settings, draw = self.install(directory)
                runtime = feature.runtime
                bundle_path = (directory / bundle).resolve()
                self.assertEqual(runtime.deferred_bundles, {bundle_path})
                self.assertEqual(runtime.run('typeof globalThis.' + symbol), 'undefined')
                self.assertTrue(settings)
                description = json.loads(runtime.call('veuszDescribe', ''))
                props = {'on': True}
                expected = [bundle_path]
                if name == 'mathjax':
                    # Select an actually shipped, non-default external font.
                    heads = engine.feature_js_heads(directory)
                    candidates = []
                    for head in heads:
                        if head['file'].startswith('fonts/'):
                            for line in head['head'].splitlines():
                                if line.startswith('// MATHJAX-FONT '):
                                    data = json.loads(line[len('// MATHJAX-FONT '):])
                                    candidates.extend((f['id'], head['file']) for f in data.get('fonts', []))
                    self.assertTrue(candidates, 'need a shipped external font')
                    font_id, font_file = candidates[0]
                    font_prop = next(p for p in description['properties'] if p['name'] == 'font')
                    self.assertNotEqual(font_id, font_prop.get('default'))
                    self.assertIn(font_id, json.dumps(font_prop))
                    props['font'] = font_id
                    expected.append((directory / font_file).resolve())
                before = set(runtime.loaded_scripts)
                with patch.object(runtime, 'eval_file', wraps=runtime.eval_file) as evaluate:
                    self.assertIsNone(draw(on=False))
                    self.assertIsNone(draw('', **props))
                    self.assertEqual(runtime.loaded_scripts, before)
                    self.assertEqual(runtime.run('typeof globalThis.' + symbol), 'undefined')
                    evaluate.assert_not_called()
                    # Pin the first reply independently; the hook must consume
                    # both bundle and font replies in this one cold draw.
                    self.assertEqual(json.loads(feature.render('x', 20, None, props)), {'load': bundle})
                    cold = draw(**props)
                    self.assertIn(output, cold)
                    self.assertNotIn('error', cold)
                    self.assertEqual([call.args[0] for call in evaluate.call_args_list], expected)
                    self.assertEqual(runtime.loaded_scripts - before, set(expected))
                    for text in ['x', 'y', 'x']:
                        self.assertIn(output, draw(text, **props))
                    self.assertEqual(evaluate.call_count, len(expected))
                    self.assertIs(platform.feature_runtime(feature.entry, directory), runtime)
                    self.assertEqual(evaluate.call_count, len(expected))

    def test_missing_and_broken_bundles_report_render_errors(self):
        with fixture_directory() as directory:
            (directory / 'feature.js').write_text(
                '// VEUSZ-DEFER ["missing.js", "broken.js"]\n'
                'veusz.feature({name: "brokenload", target: "text"});\n'
                'veusz.renderText(function () { return null; });\n', encoding='utf-8')
            (directory / 'broken.js').write_text('throw new Error("broken bundle");', encoding='utf-8')
            for name, reason in [('missing.js', 'does not have'), ('broken.js', 'broken bundle')]:
                with self.subTest(name=name):
                    platform, feature, settings, draw = self.install(directory)
                    with patch.object(feature, 'render', return_value=json.dumps({'load': name})) as render:
                        reply = draw()
                    self.assertIn(name, reply['error'])
                    self.assertIn(reason, reply['error'])
                    self.assertNotIn((directory / name).resolve(), feature.runtime.loaded_scripts)
                    self.assertEqual(render.call_count, 1)
                    self.assertTrue(any(name in note and 'could not be read' in note for note in platform.state.notes))
                    feature.runtime.close()

    def test_repeated_canonical_paths_and_32_load_limit(self):
        with fixture_directory() as directory:
            names = ['bundle%d.js' % i for i in range(33)]
            for name in names:
                (directory / name).write_text('// empty bundle\n', encoding='utf-8')
            (directory / 'feature.js').write_text(
                '// VEUSZ-DEFER ' + json.dumps(names) + '\n'
                'veusz.feature({name: "loadguard", target: "text"});\n'
                'veusz.renderText(function () { return null; });\n', encoding='utf-8')
            for requests, count in [(['bundle0.js', './bundle0.js'], 1), (names, 32)]:
                with self.subTest(count=count):
                    platform, feature, settings, draw = self.install(directory)
                    with patch.object(feature, 'render', side_effect=[json.dumps({'load': n}) for n in requests]) as render, \
                         patch.object(feature.runtime, 'eval_file', wraps=feature.runtime.eval_file) as evaluate:
                        reply = draw()
                    self.assertIn('repeated or excessive deferred load', reply['error'])
                    self.assertEqual(evaluate.call_count, count)
                    self.assertEqual(render.call_count, count + 1)
                    self.assertTrue(any('could not be read' in note for note in platform.state.notes))
                    feature.runtime.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
