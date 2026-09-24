"""Native formatting-page integration regressions; only ../upstream-veusz.

Run: python features/molecule3d/test/test_molecule3d_formatting.py
No host sources or user preferences are modified. Screenshots live in build/.
"""
import copy
import hashlib
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_molecule3d_test_helpers', HERE / 'test_molecule3d_feature.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
qt, engine, veusz, APP = base.qt, base.engine, base.veusz, base.APP
from veusz.windows import treeeditwindow as tree

PAGES = {
    'View': ['renderMode', 'scale', 'atomRadiusScale', 'pitch', 'yaw', 'roll'],
    'Appearance': ['shading', 'shadingLevels', 'shadingBrightness', 'shadingContrast',
                   'colored', 'palette', 'textureScale', 'elementTextures'],
    'Lighting': ['lightAzimuth', 'lightElevation', 'castShadows', 'shadowStrength'],
    'Labels': ['labels', 'labelHydrogens', 'labelSize', 'font', 'color'],
}
FORMATTED = {name for members in PAGES.values() for name in members}
OUT = base.PROJECT / 'build-test-molecule3d'


class FormattingTests(unittest.TestCase):
    setUp = base.Molecule3dTests.setUp
    request = base.Molecule3dTests.request
    call = base.Molecule3dTests.call
    first = base.Molecule3dTests.first
    render = base.Molecule3dTests.render

    def proxy(self, widgets=None):
        if widgets is None:
            return tree.SettingsProxySingle(self.doc, self.settings, self.widget.actions)
        return tree.SettingsProxyMulti(self.doc, widgets)

    def pages(self, proxy):
        return {p.name: p for p in proxy.settingsProxyList() if p.name in PAGES}

    def tabs(self, proxy):
        tabs = tree.TabbedFormatting(self.doc, proxy, shownames=True)
        self.addCleanup(tabs.deleteLater)
        for index in range(tabs.count()):
            tabs.slotCurrentChanged(index)
        return tabs

    def plist(self, tabs, name):
        index = tabs.tabtitles.index(name)
        tabs.setCurrentIndex(index)
        tabs.slotCurrentChanged(index)
        return tabs.widget(index).findChild(tree.PropertyList)

    @contextmanager
    def window(self):
        fake = copy.copy(veusz.setting.settingdb)
        fake.database = dict(veusz.setting.settingdb.database)
        interface = veusz.document.CommandInterface
        missing = {n for n in interface.safe_commands + interface.import_commands if not hasattr(interface, n)}
        self.assertLessEqual(missing, {'ImportFITSFile'})
        APP.clipboard().setMimeData(qt.QMimeData())
        with patch.object(qt, 'QSettings', base.MemoryQSettings), \
             patch.object(veusz.setting, 'settingdb', fake), \
             patch.object(interface, 'safe_commands', [n for n in interface.safe_commands if n not in missing]), \
             patch.object(interface, 'import_commands', [n for n in interface.import_commands if n not in missing]):
            window = veusz.windows.mainwindow.MainWindow()
            try:
                yield window
            finally:
                window.document.setModified(False)
                window.close()
                window.deleteLater()
                APP.processEvents()

    def test_flags_and_properties_preserve_original_root_settings(self):
        self.assertEqual(self.settings.getNames()[:2], ['model', 'xyz'])
        for name in FORMATTED:
            self.assertTrue(self.settings.get(name).formatting, name)
            self.assertIs(self.settings.get(name).parent, self.settings)
        for name in ('model', 'xyz', 'xPos', 'yPos', 'rotate'):
            self.assertFalse(self.settings.get(name).formatting, name)
        self.assertFalse(set(PAGES) & set(self.settings.getNames()))
        properties = tree.PropertyList(self.doc, showformatsettings=False)
        self.addCleanup(properties.deleteLater)
        properties.updateProperties(self.proxy(), showformatting=False)
        visible = set(properties.setncntrls)
        self.assertTrue({'model', 'xyz', 'xPos', 'yPos', 'rotate'} <= visible)
        self.assertFalse(FORMATTED & visible)

    def test_actual_native_tabs_have_unique_members_titles_icons(self):
        proxy = self.proxy()
        pages = self.pages(proxy)
        self.assertEqual(set(pages), set(PAGES))
        root_names = {s.name for s in proxy.settingList()}
        self.assertFalse(root_names & FORMATTED)
        tabs = self.tabs(proxy)
        self.assertIs(type(tabs), tree.TabbedFormatting)
        self.assertEqual(tabs.tabtitles, ['Main'] + list(PAGES))
        all_members = []
        self.assertEqual(set(self.plist(tabs, 'Main').setncntrls), {'hide', 'clip'})
        for name, members in PAGES.items():
            index = tabs.tabtitles.index(name)
            page = pages[name]
            self.assertEqual([s.name for s in page.settingList()], members)
            self.assertEqual(page.usertext(), name)
            self.assertEqual(page.setnsmode(), 'formatting')
            self.assertFalse(tabs.tabIcon(index).isNull())
            self.assertEqual(tabs.tabToolTip(index), name)
            controls = self.plist(tabs, name).setncntrls
            self.assertEqual(set(controls), set(members))
            for member in page.settingList():
                self.assertIs(member, self.settings.get(member.name))
                self.assertIs(member.parent, self.settings)
            all_members.extend(controls)
        self.assertEqual(len(all_members), len(set(all_members)))

    def test_native_control_signal_edit_undo_reset_and_renderer(self):
        tabs = self.tabs(self.proxy())
        plist = self.plist(tabs, 'View')
        setting = self.settings.get('scale')
        controller = plist.setncntrls['scale'][1]
        before, _ = self.render({'model': 'water', 'shading': 'none', 'scale': setting.get()})
        controller.sigSettingChanged.emit(controller, setting, 30.0)
        self.assertEqual(self.settings.scale, 30)
        after, _ = self.render({'model': 'water', 'shading': 'none', 'scale': self.settings.scale})
        self.assertGreater(after['width'], before['width'])
        self.assertEqual(self.doc.resolveSettingPath(None, self.widget.path + '/scale').get(), 30)
        self.doc.undoOperation()
        self.assertEqual(self.settings.scale, 18)
        self.doc.redoOperation()
        plist._setnsproxy.resetToDefault('scale')
        self.assertEqual(self.settings.scale, 18)
        self.doc.undoOperation()
        self.assertEqual(self.settings.scale, 30)

    def test_native_mode_shadow_edit_undo_reset_and_fast_saved_state(self):
        tabs = self.tabs(self.proxy())
        view = self.plist(tabs, 'View')
        lighting = self.plist(tabs, 'Lighting')
        mode = view.setncntrls['renderMode'][1]
        self.assertIsInstance(mode, qt.QComboBox)
        self.assertEqual([mode.itemText(i) for i in range(mode.count())], ['precise', 'fast'])
        self.assertEqual(self.settings.renderMode, 'precise')

        def edit(page, name, value):
            setting = self.settings.get(name)
            controller = page.setncntrls[name][1]
            controller.sigSettingChanged.emit(controller, setting, value)
            self.assertEqual(self.doc.resolveSettingPath(None, self.widget.path + '/' + name).get(), value)

        edit(lighting, 'castShadows', True)
        self.doc.undoOperation()
        self.assertFalse(self.settings.castShadows)
        self.doc.redoOperation()
        edit(lighting, 'shadowStrength', .6)
        self.doc.undoOperation()
        self.assertEqual(self.settings.shadowStrength, .8)
        self.doc.redoOperation()
        edit(view, 'renderMode', 'fast')
        self.assertTrue(self.settings.castShadows)
        self.assertEqual(self.settings.shadowStrength, .6)
        # Controls stay editable in fast, but their stored state is not effective.
        edit(lighting, 'shadowStrength', .35)
        fast, _ = self.render(self.feature.read(self.settings))
        self.assertNotIn('error', fast)
        edit(lighting, 'castShadows', False)
        fast_off, _ = self.render(self.feature.read(self.settings))
        self.assertEqual(fast['svg'], fast_off['svg'])
        self.doc.undoOperation()
        self.assertTrue(self.settings.castShadows)
        edit(view, 'renderMode', 'precise')
        self.assertTrue(self.settings.castShadows)
        self.assertEqual(self.settings.shadowStrength, .35)
        precise, _ = self.render(self.feature.read(self.settings))
        self.assertNotIn('error', precise)
        self.assertNotEqual(precise['svg'], fast['svg'])
        self.doc.undoOperation()
        self.assertEqual(self.settings.renderMode, 'fast')
        self.assertTrue(self.settings.castShadows)
        self.assertEqual(self.settings.shadowStrength, .35)
        self.doc.redoOperation()
        self.assertEqual(self.render(self.feature.read(self.settings))[0], precise)
        for page, name, default in [(view, 'renderMode', 'precise'),
                                    (lighting, 'castShadows', False),
                                    (lighting, 'shadowStrength', .8)]:
            before = self.settings.get(name).get()
            page._setnsproxy.resetToDefault(name)
            self.assertEqual(self.settings.get(name).get(), default)
            if before != default:
                self.doc.undoOperation()
                self.assertEqual(self.settings.get(name).get(), before)

    def test_appearance_shading_controls_edit_undo_reset_at_root(self):
        tabs = self.tabs(self.proxy())
        plist = self.plist(tabs, 'Appearance')
        for name, default, changed in [('shadingLevels', '16', '64'),
                                       ('shadingBrightness', 0, -.5),
                                       ('shadingContrast', 1.2, 2.25)]:
            with self.subTest(name=name):
                setting = self.settings.get(name)
                control = plist.setncntrls[name][1]
                self.assertEqual(setting.get(), default)
                if name == 'shadingLevels':
                    self.assertIsInstance(control, qt.QComboBox)
                    self.assertEqual([control.itemText(i) for i in range(control.count())],
                                     ['4', '8', '16', '32', '64'])
                control.sigSettingChanged.emit(control, setting, changed)
                self.assertEqual(setting.get(), changed)
                self.assertEqual(self.doc.resolveSettingPath(
                    None, self.widget.path + '/' + name).get(), changed)
                self.doc.undoOperation()
                self.assertEqual(setting.get(), default)
                self.doc.redoOperation()
                self.assertEqual(setting.get(), changed)
                plist._setnsproxy.resetToDefault(name)
                self.assertEqual(setting.get(), default)
                self.doc.undoOperation()
                self.assertEqual(setting.get(), changed)
                plist._setnsproxy.resetToDefault(name)

    def test_hydrogen_label_control_and_radius_default_reset(self):
        tabs = self.tabs(self.proxy())
        labels = self.plist(tabs, 'Labels')
        hydrogen = self.settings.get('labelHydrogens')
        controller = labels.setncntrls['labelHydrogens'][1]
        self.assertTrue(hydrogen.get())
        controller.sigSettingChanged.emit(controller, hydrogen, False)
        self.assertFalse(self.settings.labelHydrogens)
        self.doc.undoOperation()
        self.assertTrue(self.settings.labelHydrogens)
        self.doc.redoOperation()
        labels._setnsproxy.resetToDefault('labelHydrogens')
        self.assertTrue(self.settings.labelHydrogens)
        view = self.plist(tabs, 'View')
        radius = self.settings.get('atomRadiusScale')
        self.assertEqual(radius.get(), 0.75)
        control = view.setncntrls['atomRadiusScale'][1]
        control.sigSettingChanged.emit(control, radius, 1.0)
        self.assertEqual(radius.get(), 1.0)
        view._setnsproxy.resetToDefault('atomRadiusScale')
        self.assertEqual(radius.get(), 0.75)

    def test_same_type_multi_native_signal_multivalued_and_reset(self):
        self.commands.Add('molecule3d', name='second')
        other = self.doc.resolveWidgetPath(None, '/' + self.page + '/second')
        other.settings.scale = 24
        proxy = self.proxy([self.widget, other])
        pages = self.pages(proxy)
        self.assertEqual(set(pages), set(PAGES))
        view = pages['View']
        self.assertTrue(view.multivalued('scale'))
        tabs = self.tabs(proxy)
        plist = self.plist(tabs, 'View')
        controller = plist.setncntrls['scale'][1]
        notifications = []
        self.settings.get('scale').onmodified.onModified.connect(lambda: notifications.append('first'))
        other.settings.get('scale').onmodified.onModified.connect(lambda: notifications.append('second'))
        controller.sigSettingChanged.emit(controller, self.settings.get('scale'), 33.0)
        self.assertEqual([self.settings.scale, other.settings.scale], [33, 33])
        self.assertEqual(set(notifications), {'first', 'second'})
        self.assertFalse(view.multivalued('scale'))
        self.doc.undoOperation()
        self.assertEqual([self.settings.scale, other.settings.scale], [18, 24])
        view.onSettingChangedIteratively(None, self.settings.get('yaw'), [12, 34])
        self.assertEqual([self.settings.yaw, other.settings.yaw], [12, 34])
        self.doc.undoOperation()
        self.assertEqual([self.settings.yaw, other.settings.yaw], [15, 15])
        view.resetToDefault('scale')
        self.assertEqual([self.settings.scale, other.settings.scale], [18, 18])
        self.doc.undoOperation()
        self.assertEqual([self.settings.scale, other.settings.scale], [18, 24])

    def test_mixed_selection_and_other_widgets_keep_native_behavior(self):
        smiles = base.PROJECT / 'features/smiles'
        veusz.document.thefactory.regwidgets.pop('smiles', None)
        feature = engine.install_js_feature(self.platform, smiles / 'feature.js', smiles, 'smiles')
        self.addCleanup(feature.runtime.close)
        self.commands.Add('smiles', name='flat')
        flat = self.doc.resolveWidgetPath(None, '/' + self.page + '/flat')
        self.assertFalse(self.pages(self.proxy([self.widget, flat])))
        mixed = self.proxy([self.widget, flat])
        self.assertTrue({'font', 'color'} <= {s.name for s in mixed.settingList()})
        single = tree.SettingsProxySingle(self.doc, flat.settings, flat.actions)
        self.assertFalse(self.pages(single))
        self.assertTrue({'smiles', 'colored', 'size'} <= {s.name for s in single.settingList()})
        self.commands.Add('label', name='caption')
        label = self.doc.resolveWidgetPath(None, '/' + self.page + '/caption')
        ordinary = tree.SettingsProxySingle(self.doc, label.settings, label.actions)
        self.assertIn('Text', {p.name for p in ordinary.settingsProxyList()})
        self.assertNotIn('View', {p.name for p in ordinary.settingsProxyList()})

    def test_old_flat_document_roundtrip_no_page_paths(self):
        self.settings.scale = 27
        self.settings.yaw = 41
        self.settings.labels = True
        self.settings.font = 'Times New Roman'
        self.settings.shadingLevels = '8'
        self.settings.shadingBrightness = .3
        self.settings.shadingContrast = .75
        path = OUT / 'formatting-flat-roundtrip.vsz'
        self.doc.save(str(path))
        text = path.read_text(encoding='utf-8')
        for name in PAGES:
            self.assertNotIn(name + '/', text)
        self.assertIn("Set('scale', 27", text)
        # This is a legacy-style flat document: no new settings are serialized.
        for name in ('renderMode', 'castShadows', 'shadowStrength'):
            self.assertNotIn("Set('%s'," % name, text)
        doc = veusz.document.Document()
        interface = veusz.document.CommandInterface
        with patch.object(interface, 'safe_commands', [n for n in interface.safe_commands if hasattr(interface, n)]):
            doc.load(str(path))
        loaded = doc.resolveWidgetPath(None, self.widget.path)
        self.assertEqual(loaded.settings.renderMode, 'precise')
        self.assertFalse(loaded.settings.castShadows)
        self.assertEqual(loaded.settings.shadowStrength, .8)
        self.assertEqual(loaded.settings.scale, 27)
        self.assertEqual(loaded.settings.yaw, 41)
        self.assertTrue(loaded.settings.labels)
        self.assertEqual(loaded.settings.font, 'Times New Roman')
        for name, value in [('shadingLevels', '8'), ('shadingBrightness', .3),
                            ('shadingContrast', .75)]:
            self.assertEqual(getattr(loaded.settings, name), value)
            self.assertIs(loaded.settings.get(name).parent, loaded.settings)
            self.assertIn("Set('%s'," % name, text)
        self.assertFalse(set(PAGES) & set(loaded.settings.getNames()))

    def test_generic_page_uses_declared_storage_name_not_handle(self):
        root = OUT / 'formatting-storage-feature'
        root.mkdir(exist_ok=True)
        entry = root / 'feature.js'
        entry.write_text('''veusz.feature({name:'formatting_storage_demo',target:'widget',
 formattingPages:[{name:'Look',title:'Custom look',icon:'settings_main',settings:['stored_level']}]});
veusz.number('level',{setting:'stored_level',default:2});
veusz.renderWidget(function(req){return veusz.svg('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="4"/></svg>',{width:10,height:10});});''', encoding='utf-8')
        feature = engine.install_js_feature(self.platform, entry, root, 'formatting_storage_demo')
        self.addCleanup(feature.runtime.close)
        self.commands.Add('formatting_storage_demo', name='generic')
        widget = self.doc.resolveWidgetPath(None, '/' + self.page + '/generic')
        proxy = tree.SettingsProxySingle(self.doc, widget.settings, widget.actions)
        pages = {p.name: p for p in proxy.settingsProxyList()}
        page = pages['Look']
        self.assertEqual(page.usertext(), 'Custom look')
        self.assertEqual([s.name for s in page.settingList()], ['stored_level'])
        original = widget.settings.get('stored_level')
        self.assertIs(page.settingList()[0], original)
        self.assertIs(original.parent, widget.settings)
        page.onSettingChanged(None, original, 7.0)
        self.assertEqual(widget.settings.stored_level, 7)
        self.assertEqual(feature.read(widget.settings)['level'], 7)
        self.doc.undoOperation()
        self.assertEqual(widget.settings.stored_level, 2)
        self.assertNotIn('Look', widget.settings.getNames())
        self.assertNotIn('level', widget.settings.getNames())

    def test_invalid_page_declarations_fail_before_factory_registration(self):
        cases = [
            {},
            [None],
            [{'name': 'Bad/name', 'settings': ['stored_level']}],
            [{'name': 'stored_level', 'settings': ['stored_level']}],
            [{'name': 'Look', 'settings': []}],
            [{'name': 'Look', 'settings': ['level']}],
            [{'name': 'Look', 'settings': ['missing']}],
            [{'name': 'Look', 'settings': ['Fill']}],
            [{'name': 'Look', 'title': '', 'settings': ['stored_level']}],
            [{'name': 'Look', 'icon': '', 'settings': ['stored_level']}],
            [{'name': 'Look', 'settings': ['stored_level', 'stored_level']}],
            [{'name': 'One', 'settings': ['stored_level']}, {'name': 'Two', 'settings': ['stored_level']}],
            [{'name': 'Same', 'settings': ['stored_level']}, {'name': 'Same', 'settings': ['font']}],
        ]
        self.addCleanup(self.platform.close_all)
        for index, pages in enumerate(cases):
            with self.subTest(pages=pages):
                name = 'formatting_invalid_' + str(index)
                root = OUT / name
                root.mkdir(exist_ok=True)
                entry = root / 'feature.js'
                declaration = dict(name=name, target='widget', formattingPages=pages)
                entry.write_text('veusz.feature(' + json.dumps(declaration) + ');\n'
                                 "veusz.number('level',{setting:'stored_level',default:2});\n", encoding='utf-8')
                with self.assertRaises(engine.JsEngineError):
                    engine.install_js_feature(self.platform, entry, root, name)
                self.assertNotIn(name, veusz.document.thefactory.regwidgets)

    def test_invalid_property_position_is_rejected(self):
        self.addCleanup(self.platform.close_all)
        for index, posn in enumerate((True, '1', 1.5)):
            with self.subTest(posn=posn):
                name = 'formatting_invalid_posn_' + str(index)
                root = OUT / name
                root.mkdir(exist_ok=True)
                entry = root / 'feature.js'
                declaration = dict(name=name, target='widget')
                prop = dict(default=2, posn=posn)
                entry.write_text('veusz.feature(' + json.dumps(declaration) + ');\n'
                                 'veusz.number("level",' + json.dumps(prop) + ');\n', encoding='utf-8')
                with self.assertRaises(engine.JsEngineError):
                    engine.install_js_feature(self.platform, entry, root, name)
                self.assertNotIn(name, veusz.document.thefactory.regwidgets)

    def test_real_mainwindow_properties_pages_and_screenshots(self):
        with self.window() as window:
            commands = veusz.document.CommandInterface(window.document)
            page = commands.Add('page')
            commands.To(page)
            commands.Add('molecule3d', name='molecule')
            commands.Set('molecule/scale', 45.0)
            commands.Set('molecule/labels', True)
            widget = window.document.resolveWidgetPath(None, '/' + page + '/molecule')
            window.resize(1400, 960)
            window.show()
            window.treeedit.selectWidget(widget)
            APP.processEvents()
            properties = window.findChild(tree.PropertiesDock)
            formatting = window.findChild(tree.FormatDock)
            self.assertIsNotNone(properties)
            self.assertIsNotNone(formatting)
            # A pre-imported SettingDB can restore the user's tabified layout.
            # Normalize only this isolated test window, without persisting state.
            docks = [window.treeedit, properties, formatting]
            for dock in docks:
                window.removeDockWidget(dock)
                dock.setFloating(False)
            for dock in docks:
                window.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
            window.splitDockWidget(window.treeedit, properties, qt.Qt.Orientation.Vertical)
            window.splitDockWidget(properties, formatting, qt.Qt.Orientation.Vertical)
            for dock in docks:
                dock.show()
                dock.raise_()
                self.assertFalse(set(window.tabifiedDockWidgets(dock)) & set(docks))
            window.resizeDocks([window.treeedit, properties, formatting], [160, 360, 330], qt.Qt.Orientation.Vertical)
            window.resizeDocks([window.treeedit], [380], qt.Qt.Orientation.Horizontal)
            APP.processEvents()
            self.assertTrue({'model', 'xyz'} <= set(properties.proplist.setncntrls))
            self.assertFalse(FORMATTED & set(properties.proplist.setncntrls))
            tabs = formatting.tabwidget
            self.assertIs(type(tabs), tree.TabbedFormatting)
            self.assertEqual(tabs.tabtitles, ['Main'] + list(PAGES))
            build = base.PROJECT / 'build'
            build.mkdir(exist_ok=True)
            screenshots = []
            for name in ('View', 'Labels', 'Appearance', 'Lighting'):
                plist = self.plist(tabs, name)
                APP.processEvents()
                APP.processEvents()
                self.assertTrue(formatting.isVisibleTo(window))
                for member, (_label, control) in plist.setncntrls.items():
                    self.assertTrue(control.isVisibleTo(window), (name, member))
                    self.assertFalse(control.visibleRegion().isEmpty(), (name, member))
                    rect = qt.QRect(control.mapTo(window, qt.QPoint(0, 0)), control.size())
                    self.assertTrue(window.rect().contains(rect), (name, member, rect))
                for member in ('model', 'xyz'):
                    self.assertTrue(properties.proplist.setncntrls[member][1].isVisibleTo(window))
                image = window.grab()
                self.assertFalse(image.isNull())
                output = build / ('molecule3d-formatting-' + name.lower() + '.png')
                self.assertTrue(image.save(str(output)))
                screenshots.append(hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(len(set(screenshots)), 4, 'formatting page screenshots must differ')


if __name__ == '__main__':
    unittest.main(verbosity=2)
