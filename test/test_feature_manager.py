"""Feature-manager regressions against ONLY ../upstream-veusz.

Run: python test/test_feature_manager.py
No real QSettings are read or written. Fixtures inherit workspace ACLs.
"""
import os
from pathlib import Path
import shutil
import sys
import types
import unittest
from unittest import mock
import uuid

PROJECT = Path(__file__).resolve().parents[1]
UPSTREAM = PROJECT.parent / 'upstream-veusz'
os.environ['VEUSZ_JS_ENGINE_DEFER'] = '1'
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(UPSTREAM))

import veusz
assert Path(veusz.__file__).resolve().is_relative_to(UPSTREAM), veusz.__file__
import veusz.qtall as qt


class MemoryQSettings:
    """Prevent even import-time access to the user's preference backend."""
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


# The upstream singleton reads settings at import time; isolate that too.
with mock.patch.object(qt, 'QSettings', MemoryQSettings):
    import veusz.setting as setting
    import veusz.utils as utils
    import veusz.windows.mainwindow as mainwindow

import veusz_js_engine as engine


class FakeDatabase(dict):
    def __init__(self, disabled=()):
        super().__init__({engine.FEATURE_DISABLED_KEY: list(disabled)})
        self.writes = 0
        self.fail_write = False

    def writeSettings(self):
        self.writes += 1
        if self.fail_write:
            raise OSError('fixture persistence failure')


class FeatureManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.root = PROJECT / ('build-test-feature-manager-' + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.features = self.root / 'features'
        self.features.mkdir()
        self.db = FakeDatabase()
        self.patch(setting, 'settingdb', self.db)
        self.patch(qt, 'QSettings', MemoryQSettings)
        self.patch(engine, 'find_feature_dirs', lambda here: [self.features])
        self.platform = engine.Platform(self.root)
        self.windows = []
        self.addCleanup(self.close_windows)

    def patch(self, obj, name, value):
        patcher = mock.patch.object(obj, name, value)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def close_windows(self):
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.app.processEvents()

    def fixture(self, relative, source='raise RuntimeError("MUST NOT EXECUTE")\n'):
        path = self.features / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
        return path

    def test_dry_discovery_includes_disabled_and_invalid_code(self):
        first = self.fixture('alpha/feature.js', 'not valid JavaScript !!!')
        self.fixture('alpha/feature.py')
        self.fixture('beta.py')
        self.fixture('gamma.js')
        self.fixture('_helper.py')
        self.fixture('.hidden/feature.js')
        self.fixture('not_a_feature/helper.py')
        extra = self.root / 'extra'
        extra.mkdir()
        (extra / 'alpha.py').write_text('invalid python !!!', encoding='utf-8')
        self.patch(engine, 'find_feature_dirs', lambda here: [self.features, extra])
        self.db[engine.FEATURE_DISABLED_KEY] = ['alpha']
        with mock.patch.object(engine, 'install_js_feature') as js, \
                mock.patch.object(engine, '_run_python_feature') as py:
            found = engine.discover_features(self.root)
        self.assertEqual([name for name, _ in found], ['alpha', 'beta', 'gamma'])
        self.assertEqual(dict(found)['alpha'], first)
        js.assert_not_called()
        py.assert_not_called()
        self.assertEqual(self.db.writes, 0)

    def test_malformed_preferences_are_safe(self):
        for value in (None, 'mathjax', 13, {'mathjax': False}, {'mathjax'}):
            with self.subTest(value=value):
                self.db[engine.FEATURE_DISABLED_KEY] = value
                self.assertEqual(engine.disabled_feature_preferences(self.db), set())
        self.db[engine.FEATURE_DISABLED_KEY] = ['a', 3, None, 'a', 'b']
        self.assertEqual(engine.disabled_feature_preferences(), {'a', 'b'})
        self.db[engine.FEATURE_DISABLED_KEY] = ('tuple',)
        self.assertEqual(engine.disabled_feature_preferences(), {'tuple'})

    def test_save_retains_unknown_names_and_rolls_back_failed_write(self):
        self.db[engine.FEATURE_DISABLED_KEY] = ['absent', 'on']
        engine.save_feature_preferences({'on': True, 'off': False}, self.db)
        self.assertEqual(self.db[engine.FEATURE_DISABLED_KEY], ['absent', 'off'])
        self.assertEqual(self.db.writes, 1)
        self.db.fail_write = True
        with self.assertRaises(OSError):
            engine.save_feature_preferences({'off': True}, self.db)
        self.assertEqual(self.db[engine.FEATURE_DISABLED_KEY], ['absent', 'off'])

    def test_disabled_entries_never_execute_or_register(self):
        self.fixture('js/feature.js', 'throw new Error("MUST NOT EXECUTE");')
        self.fixture('py/feature.py')
        self.fixture('enabled.py', 'pass\n')
        self.db[engine.FEATURE_DISABLED_KEY] = ['js', 'py']
        with mock.patch.object(engine, 'install_js_feature') as js, \
                mock.patch.object(engine, '_run_python_feature',
                                  wraps=engine._run_python_feature) as py, \
                mock.patch.object(self.platform, 'feature_runtime') as runtime:
            loaded, failed = engine.load_features(self.platform)
        js.assert_not_called()
        runtime.assert_not_called()
        self.assertEqual(py.call_count, 1)
        self.assertEqual(py.call_args.args[1], 'enabled')
        self.assertEqual([p.stem for p in loaded], ['enabled'])
        self.assertEqual(failed, [])
        self.assertEqual(self.platform.state.feature_names, {'enabled'})
        self.assertEqual(self.platform.state.injections, [])
        self.assertEqual(self.platform.state.draw_hooks, [])
        self.assertEqual(self.platform._runtimes, {})
        self.assertEqual(self.platform._features, [])

    def test_restart_only_snapshot_survives_saves_and_repeated_loading(self):
        self.fixture('a.py', 'pass\n')
        self.fixture('b.py', 'pass\n')
        self.db[engine.FEATURE_DISABLED_KEY] = ['a']
        with mock.patch.object(engine, '_run_python_feature',
                               wraps=engine._run_python_feature) as execute:
            engine.load_features(self.platform)
            self.assertEqual(self.platform.state.feature_names, {'b'})
            engine.save_feature_preferences({'a': True, 'b': False})
            engine.load_features(self.platform)
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(self.platform.disabled_features, {'a'})
            self.assertEqual(self.platform.state.feature_names, {'b'})
            fresh = engine.Platform(self.root)
            engine.load_features(fresh)
            self.assertEqual(fresh.disabled_features, {'b'})
            self.assertEqual(fresh.state.feature_names, {'a'})
            self.assertEqual(execute.call_count, 2)

    def dialog(self):
        dialog = engine.feature_manager_dialog(self.platform)
        self.windows.append(dialog)
        tree = dialog.findChild(qt.QTreeWidget, 'jsEngineFeatureList')
        items = {tree.topLevelItem(i).text(0): tree.topLevelItem(i)
                 for i in range(tree.topLevelItemCount())}
        buttons = dialog.findChild(qt.QDialogButtonBox)
        return dialog, items, buttons

    def test_dialog_defaults_statuses_cancel_and_save_are_global(self):
        self.fixture('a.js')
        self.fixture('b.py')
        self.fixture('failed.js')
        self.db[engine.FEATURE_DISABLED_KEY] = ['a', 'absent']
        self.platform.disabled_features = {'a'}
        self.platform.state.feature_names.add('b')
        with mock.patch.object(engine, 'install_js_feature') as execute:
            dialog, items, buttons = self.dialog()
        execute.assert_not_called()
        checked, unchecked = qt.Qt.CheckState.Checked, qt.Qt.CheckState.Unchecked
        self.assertEqual(items['a'].checkState(0), unchecked)
        self.assertEqual(items['b'].checkState(0), checked)
        self.assertEqual(items['a'].text(1), 'Disabled')
        self.assertEqual(items['b'].text(1), 'Loaded')
        self.assertEqual(items['failed'].text(1), 'Not loaded')
        items['a'].setCheckState(0, checked)
        buttons.button(qt.QDialogButtonBox.StandardButton.Cancel).click()
        self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Rejected)
        self.assertEqual(self.db.writes, 0)
        self.assertEqual(self.db[engine.FEATURE_DISABLED_KEY], ['a', 'absent'])
        dialog, items, buttons = self.dialog()
        items['a'].setCheckState(0, checked)
        items['b'].setCheckState(0, unchecked)
        buttons.button(qt.QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)
        self.assertEqual(self.db.writes, 1)
        self.assertEqual(self.db[engine.FEATURE_DISABLED_KEY], ['absent', 'b'])
        _, reopened, _ = self.dialog()
        self.assertEqual(reopened['a'].checkState(0), checked)
        self.assertEqual(reopened['b'].checkState(0), unchecked)
        self.assertEqual(self.platform.disabled_features, {'a'})

    def test_empty_dialog_and_failed_save_stays_open(self):
        dialog, items, buttons = self.dialog()
        self.assertEqual(items, {})
        self.db.fail_write = True
        with mock.patch.object(qt.QMessageBox, 'warning') as warning:
            buttons.button(qt.QDialogButtonBox.StandardButton.Save).click()
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)

    def fake_mainwindow(self):
        class Window(qt.QMainWindow):
            def __init__(self, before_menus=None):
                super().__init__()
                if before_menus is not None:
                    before_menus()
                self.menu_result = self._defineMenus()

            def _defineMenus(self):
                self.menus = {'tools': self.menuBar().addMenu('Tools')}
                return 'original-result'
        self.patch(mainwindow, 'MainWindow', Window)
        return Window

    def new_window(self, cls, *args):
        window = cls(*args)
        self.windows.append(window)
        return window

    def actions(self, window):
        return [action for action in window.menus['tools'].actions()
                if action.objectName() == 'jsEngineFeatures']

    def test_existing_future_and_reexecuted_install_have_one_action(self):
        Window = self.fake_mainwindow()
        existing = self.new_window(Window)
        self.assertEqual(self.actions(existing), [])
        engine.install_feature_manager(self.platform)
        wrapped = Window._defineMenus
        future = self.new_window(Window)
        self.assertEqual(future.menu_result, 'original-result')
        # Mirror upstream exec(source, {}) rather than an ordinary module import.
        namespace = {}
        source = (PROJECT / 'veusz_js_engine.py').read_text(encoding='ascii')
        exec(compile(source, str(PROJECT / 'veusz_js_engine.py'), 'exec'), namespace)
        namespace['install_feature_manager'](self.platform)
        engine.install_feature_manager(self.platform)
        self.assertIs(Window._defineMenus, wrapped)
        for window in (existing, future):
            self.assertEqual(len(self.actions(window)), 1)
        current = types.SimpleNamespace(here=self.root)
        with mock.patch.object(utils, engine.PUBLISH_ATTR, current, create=True), \
                mock.patch.object(engine, 'feature_manager_dialog') as dialog:
            self.actions(existing)[0].trigger()
        dialog.assert_called_once_with(current, existing)
        dialog.return_value.exec.assert_called_once()
        dialog.return_value.deleteLater.assert_called_once()

    def test_install_during_in_progress_constructor_catches_first_window(self):
        Window = self.fake_mainwindow()
        first = self.new_window(
            Window, lambda: engine.install_feature_manager(self.platform))
        self.assertEqual(len(self.actions(first)), 1)
        self.assertEqual(len(self.actions(self.new_window(Window))), 1)
        # Rebuilt menus should not lose the action or create duplicates.
        first._defineMenus()
        engine.install_feature_manager(self.platform)
        self.assertEqual(len(self.actions(first)), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
