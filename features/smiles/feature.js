// VEUSZ-DEFER ["headless.js", "smiles-drawer.js"]
/* SMILES molecular structures for Veusz. Apache-2.0, this project.
 * The upstream drawer and its small SVG adapter stay cold until first use.
 * No browser, network, Node.js or chemistry service is used at render time.
 */
(function () {
    'use strict';
    veusz.feature({name: 'smiles', title: 'SMILES molecular structures',
                   target: 'text', version: '0.1.0'});
    veusz.switch('on', {
        setting: 'smiles', label: 'SMILES', default: false, row: 'molecule',
        descr: 'Interpret this text as a SMILES molecule and draw its 2D structure. '
             + 'Use only one renderer (SMILES, MathJax or KaTeX) per text element.'
    });
    veusz.switch('colored', {
        setting: 'smilesColored', label: 'Element colors', default: true,
        row: 'molecule',
        descr: 'Use element colors; off draws the structure in the text color.'
    });
    veusz.number('scale', {
        setting: 'smilesScale', label: 'Structure scale', default: 1,
        descr: 'Scale the structure relative to the text font size (0.1 to 10).'
    });

    var cache = Object.create(null);
    var cacheSize = 0;
    veusz.renderText(function (req) {
        if (!req.on('on')) { return null; }
        var source = String(req.text == null ? '' : req.text).trim();
        if (!source) { return null; }
        if (source.length > 4096) {
            return veusz.error('SMILES input is limited to 4096 characters.');
        }
        var scale = req.get('scale');
        scale = scale === undefined ? 1 : Number(scale);
        if (!isFinite(scale) || scale < 0.1 || scale > 10) {
            return veusz.error('SMILES structure scale must be between 0.1 and 10.');
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
        var size = req.size > 0 && isFinite(req.size) ? req.size : 12;
        var colored = req.get('colored') !== false;
        var color = /^#[0-9a-f]{6}$/i.test(req.color || '') ? req.color : '#000000';
        var key = JSON.stringify([source, size, scale, colored, color, req.face || '']);
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
            // Upstream labels use 11 pt, i.e. 11 * 4/3 SVG CSS pixels.
            // Match the label's font size, then apply the optional diagram scale.
            var factor = size * scale / (11 * 4 / 3);
            var reply = veusz.svg(result.svg, {width: result.width * factor,
                                               height: result.height * factor,
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
