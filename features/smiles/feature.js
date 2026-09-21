// VEUSZ-DEFER ["headless.js", "smiles-drawer.js"]
/* SMILES molecular structures for Veusz. Apache-2.0, this project.
 * The upstream drawer and its small SVG adapter stay cold until first use.
 * No browser, network, Node.js or chemistry service is used at render time.
 */
(function () {
    'use strict';
    veusz.feature({name: 'smiles', title: 'SMILES molecule',
                   target: 'widget', source: 'smiles', sizing: 'font',
                   version: '0.3.0'});
    veusz.text('smiles', {
        setting: 'smiles', label: 'SMILES', default: 'CCO',
        descr: 'SMILES molecular structure, for example CCO or c1ccccc1.'
    });
    veusz.switch('colored', {
        setting: 'colored', label: 'Element colors', default: true,
        descr: 'Use element colors; off uses the molecule widget color.'
    });

    var cache = Object.create(null);
    var cacheSize = 0;
    veusz.renderWidget(function (req) {
        var input = req.get('smiles');
        var source = String(input == null ? '' : input).trim();
        if (!source) { return null; }
        if (source.length > 4096) {
            return veusz.error('SMILES input is limited to 4096 characters.');
        }
        var size = Number(req.size);
        if (!(size > 0) || !isFinite(size)) {
            return veusz.error('SMILES font size must be positive and finite.');
        }
        if (req.discard) {
            return veusz.error('SMILES atom labels need a font with glyph outlines; '
                             + 'choose a TrueType or OpenType font.');
        }
        if (typeof globalThis.smilesToSvg !== 'function') {
            return JSON.stringify({load: 'headless.js'});
        }
        if (!globalThis.window || !globalThis.window.SmilesDrawer) {
            return JSON.stringify({load: 'smiles-drawer.js'});
        }
        var colored = req.get('colored') !== false;
        var color = /^#[0-9a-f]{6}$/i.test(req.color || '') ? req.color : '#000000';
        var key = JSON.stringify([source, size, colored, color, req.face || '']);
        if (!req.measured && cache[key] !== undefined) { return cache[key]; }
        try {
            var request = {smiles: source, measured: req.measured,
                           options: {scale: 1, fontSizeLarge: 11}};
            if (!colored) { request.color = color; }
            var result = JSON.parse(globalThis.smilesToSvg(JSON.stringify(request)));
            if (result.measure) {
                if (req.measured) {
                    return veusz.error('SMILES atom label measurements were incomplete.');
                }
                return JSON.stringify({measure: result.measure});
            }
            if (!result.svg || !(result.width > 0) || !(result.height > 0)
                    || !isFinite(result.width) || !isFinite(result.height)) {
                return veusz.error('SMILES drawer returned invalid geometry.');
            }
            // Upstream 11 pt labels occupy 11 * 4/3 SVG CSS-pixel units.
            // Return natural dimensions in points, so the widget's own font
            // size controls both atom labels and bonds, not a container box.
            var factor = size / (11 * 4 / 3);
            var width = result.width * factor;
            var height = result.height * factor;
            if (!isFinite(width) || !isFinite(height)) {
                return veusz.error('SMILES font size produced invalid dimensions.');
            }
            var reply = veusz.svg(result.svg, {width: width, height: height,
                                               depth: 0});
            if (cacheSize >= 128) { cache = Object.create(null); cacheSize = 0; }
            if (cache[key] === undefined) { cacheSize++; }
            cache[key] = reply;
            return reply;
        } catch (err) {
            return veusz.error('SMILES could not draw this structure: '
                             + (err && err.message ? err.message : err));
        }
    });
}());
