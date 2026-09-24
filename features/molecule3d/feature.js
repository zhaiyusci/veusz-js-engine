// VEUSZ-DEFER ["dot-regions.js", "boundaries.js", "wash.js", "dots.js", "renderer.js"]
/* Offline MolecularRenaissance adapter. Apache-2.0, this project.
 * Upstream runtime files retain their own provenance; see UPSTREAM.md.
 * No DOM, network, Node.js or conformer generation is used at render time.
 */
(function () {
    'use strict';
    veusz.feature({name: 'molecule3d', title: '3D molecule', target: 'widget',
                   source: 'model', sizing: 'natural', version: '0.1.0',
                   formattingPages: [
                       {name: 'View', title: 'View', icon: 'button_scene3d',
                        settings: ['scale', 'atomRadiusScale', 'pitch', 'yaw', 'roll']},
                       {name: 'Appearance', title: 'Appearance', icon: 'settings_bgfill',
                        settings: ['shading', 'colored', 'palette', 'textureScale', 'elementTextures']},
                       {name: 'Lighting', title: 'Lighting', icon: 'settings_lighting',
                        settings: ['lightAzimuth', 'lightElevation']},
                       {name: 'Labels', title: 'Labels', icon: 'settings_axislabel',
                        settings: ['labels', 'labelHydrogens', 'labelSize', 'font', 'color']}
                   ]});
    var defaults = Object.create(null);
    function property(kind, name, value, label, descr, choices, posn) {
        defaults[name] = value;
        var options = {default: value, label: label, descr: descr};
        if (posn !== undefined) { options.posn = posn; }
        if (choices) {
            options.choices = choices.map(function (v) { return {value: v, label: v}; });
        }
        veusz[kind](name, options);
    }
    property('choice', 'model', 'water', 'Model',
             'Idealized example, or embedded XYZ coordinates in angstrom.', ['water', 'ethanol', 'c60', 'xyz']);
    property('text', 'xyz', '', 'XYZ coordinates',
             'Single-frame XYZ, up to 96 atoms. Bonds are inferred from distances, not chemical valence.', null, 1);
    property('number', 'scale', 18, 'Scale (pt/angstrom)',
             'Physical projection scale, 1 to 100 points per angstrom; no automatic fitting.');
    property('number', 'atomRadiusScale', 0.75, 'Atom radius scale',
             'Multiplier of empirical covalent radii, 0.1 to 3; bond radius stays 0.115 angstrom.');
    property('number', 'pitch', -10, 'Pitch (degrees)', 'Fixed X-axis rotation.');
    property('number', 'yaw', 15, 'Yaw (degrees)', 'Fixed Y-axis rotation.');
    property('number', 'roll', 0, 'Roll (degrees)', 'Fixed Z-axis rotation after pitch and yaw.');
    property('choice', 'shading', 'hatch', 'Shading', 'Molecular engraving style.',
             ['hatch', 'stipple', 'halftone', 'none']);
    property('switch', 'colored', true, 'Element colors', 'Fill atom surfaces with element colors.');
    property('choice', 'palette', 'jmol', 'Palette', 'Element color palette.',
             ['jmol', 'rasmol', 'pymol', 'ortep']);
    property('number', 'textureScale', 1, 'Texture scale', 'Engraving mark scale, 0.2 to 2.5.');
    property('switch', 'elementTextures', false, 'Element patterns', 'Distinguish elements with surface patterns.');
    property('switch', 'labels', false, 'Element labels', 'Outline labels using the widget font and color.');
    property('switch', 'labelHydrogens', true, 'Hydrogen labels',
             'Show H symbols when element labels are enabled; turning this off keeps hydrogen atoms and bonds.');
    property('number', 'labelSize', 12, 'Label size (pt)', 'Independent label size, 6 to 72 points.');
    property('number', 'lightAzimuth', -29, 'Light azimuth (degrees)', 'Camera-fixed directional light azimuth.');
    property('number', 'lightElevation', 32, 'Light elevation (degrees)', 'Camera-fixed directional light elevation.');

    var bundles = [['MolDotRegions', 'dot-regions.js'], ['MolBoundaries', 'boundaries.js'],
                   ['MolWash', 'wash.js'], ['MolDots', 'dots.js'], ['MolEngraver', 'renderer.js']];
    var cache = new Map(), cacheBytes = 0, maxCacheBytes = 16 * 1024 * 1024;
    function escapeAttr(value) {
        return String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function bounded(p, name, lo, hi) {
        var value = p[name];
        if (typeof value !== 'number' || !Number.isFinite(value) || value < lo || value > hi) {
            throw new Error(name + ' must be a finite number from ' + lo + ' to ' + hi + '.');
        }
        return value;
    }
    function choice(p, name, allowed) {
        if (allowed.indexOf(p[name]) < 0) { throw new Error('Unknown ' + name + ': ' + p[name]); }
    }
    // Only bounding-box projection is duplicated here; all molecular geometry
    // and visibility remain upstream's. Quaternion convention is [x,y,z,w].
    function projected(p, q) {
        var tx = 2 * (q[1] * p[2] - q[2] * p[1]);
        var ty = 2 * (q[2] * p[0] - q[0] * p[2]);
        var tz = 2 * (q[0] * p[1] - q[1] * p[0]);
        return [p[0] + q[3] * tx + q[1] * tz - q[2] * ty,
                p[1] + q[3] * ty + q[2] * tx - q[0] * tz];
    }
    function outlinedLabels(svg, measured, centers) {
        return svg.replace(/<text\b([^>]*)>([^<]*)<\/text>/g, function (_, raw, element) {
            var attrs = Object.create(null);
            raw.replace(/([\w:-]+)="([^"]*)"/g, function (_, name, value) { attrs[name] = value; });
            var run = measured[element];
            if (!run || !run.path) { throw new Error('Missing outline for element ' + element); }
            var fontSize = Number(attrs['font-size']), k = fontSize / 1000;
            var ink = run.ink, center = centers[attrs['data-surface-id']];
            if (!ink || !center || ![ink.x, ink.y, ink.w, ink.h].every(Number.isFinite)) {
                throw new Error('Element labels require measured ink bounds.');
            }
            // Metrics are in em; only path coordinates use 1000 units/em.
            // Center visible ink, not advance width or a font-specific baseline.
            var x = center[0] - (ink.x + ink.w / 2) * fontSize;
            var y = center[1] - (ink.y + ink.h / 2) * fontSize;
            if (!(k > 0) || !Number.isFinite(x) || !Number.isFinite(y)) {
                throw new Error('Invalid label geometry.');
            }
            var strokeWidth = Number(attrs['stroke-width']) / k;
            var preserved = '';
            Object.keys(attrs).forEach(function (name) {
                if (/^(data-[\w-]+|opacity|clip-path|mask|visibility)$/.test(name)) {
                    preserved += ' ' + name + '="' + attrs[name] + '"';
                }
            });
            var d = escapeAttr(run.path);
            // Two paths, not paint-order: Qt must paint the halo before the glyph.
            // Replace each text in place, retaining upstream surface occlusion.
            return '<g' + preserved + ' transform="translate(' + x + ' ' + y + ') scale(' + k + ')">'
                + '<path d="' + d + '" fill="none" stroke="' + (attrs.stroke || '#ffffff')
                + '" stroke-width="' + strokeWidth + '" stroke-linejoin="round"/>'
                + '<path d="' + d + '" stroke="none" fill="' + (attrs.fill || '#000000') + '"/></g>';
        });
    }
    function qtSvg(svg, canvasW, canvasH) {
        // Qt 6.11 ignores SVG clipPath. White user-space masks preserve the
        // same clipping geometry (including nested tone/silhouette regions).
        // Qt's native SVG exporter may rasterize these masked layers; the
        // source SVG itself still consists of vector geometry and patterns.
        svg = svg.replace(/<clipPath\b([^>]*)>([\s\S]*?)<\/clipPath>/g, function (_, attrs, body) {
            attrs = attrs.replace(/\sclipPathUnits="[^"]*"/g, '');
            body = body.replace(/\bclip-rule=/g, 'fill-rule=');
            // Some upstream paths already carry both rules. Avoid duplicate
            // attributes when preserving their even-odd clipping semantics.
            body = body.replace(/(<[^>]*?)\sfill-rule="([^"]*)"([^>]*?)\sfill-rule="\2"/g, '$1 fill-rule="$2"$3');
            return '<mask' + attrs + ' maskUnits="userSpaceOnUse" maskContentUnits="userSpaceOnUse"'
                + ' x="' + (-canvasW) + '" y="' + (-canvasH) + '" width="' + (canvasW * 3)
                + '" height="' + (canvasH * 3) + '"><g fill="#ffffff" stroke="none">' + body + '</g></mask>';
        }).replace(/\bclip-path=/g, 'mask=');
        // QSvgRenderer drops zero-length subpaths from compound stipple paths.
        // A round cap on a zero-length line is exactly a filled circle.
        return svg.replace(/<path\b([^>]*\bdata-stipple-radius="[^"]*"[^>]*)\/>/g, function (original, raw) {
            var attrs = Object.create(null);
            raw.replace(/([\w:-]+)="([^"]*)"/g, function (_, name, value) { attrs[name] = value; });
            var pattern = /M(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)h0/g;
            var d = attrs.d || '', radius = Number(attrs['stroke-width']) / 2;
            if (!(radius > 0) || d.replace(pattern, '').trim()) { return original; }
            var circles = d.replace(pattern, function (_, x, y) {
                return '<circle cx="' + x + '" cy="' + y + '" r="' + radius + '"/>';
            });
            return '<g data-stipple-radius="' + attrs['data-stipple-radius'] + '" fill="'
                + (attrs.stroke || '#161616') + '" stroke="none">' + circles + '</g>';
        });
    }
    veusz.renderWidget(function (req) {
        try {
            var p = Object.create(null);
            Object.keys(defaults).forEach(function (name) {
                var value = req.get(name);
                p[name] = value === undefined ? defaults[name] : value;
            });
            choice(p, 'model', ['water', 'ethanol', 'c60', 'xyz']);
            if (typeof p.xyz !== 'string') { throw new Error('XYZ coordinates must be text.'); }
            if (p.model === 'xyz' && !p.xyz.trim()) { return null; }
            if (p.xyz.length > 65536) { throw new Error('XYZ input is limited to 65536 characters.'); }
            choice(p, 'shading', ['hatch', 'stipple', 'halftone', 'none']);
            choice(p, 'palette', ['jmol', 'rasmol', 'pymol', 'ortep']);
            bounded(p, 'scale', 1, 100);
            bounded(p, 'atomRadiusScale', 0.1, 3);
            bounded(p, 'textureScale', 0.2, 2.5);
            bounded(p, 'labelSize', 6, 72);
            ['pitch', 'yaw', 'roll', 'lightAzimuth', 'lightElevation'].forEach(function (name) {
                bounded(p, name, -36000, 36000);
            });
            ['colored', 'elementTextures', 'labels', 'labelHydrogens'].forEach(function (name) {
                if (typeof p[name] !== 'boolean') { throw new Error(name + ' must be true or false.'); }
            });
            var color = /^#[0-9a-f]{6}$/i.test(req.color || '') ? req.color : '#000000';
            var key = JSON.stringify([p, p.labels ? (req.face || '') : '', p.labels ? color : '']);
            if (!req.measured && cache.has(key)) {
                var hit = cache.get(key);
                cache.delete(key); cache.set(key, hit);
                return hit.reply;
            }
            for (var i = 0; i < bundles.length; i++) {
                if (!globalThis[bundles[i][0]]) { return JSON.stringify({load: bundles[i][1]}); }
            }
            var engine = globalThis.MolEngraver;
            var molecule = p.model === 'xyz'
                ? engine.parseXYZ(p.xyz, {inferBonds: true, maxAtoms: 96}) : engine.examples[p.model];
            if (!molecule || !Array.isArray(molecule.atoms) || !molecule.atoms.length
                    || molecule.atoms.length > 96 || !Array.isArray(molecule.bonds)
                    || molecule.bonds.length > 256) {
                throw new Error('Molecules are limited to 96 atoms and 256 bonds.');
            }
            var runs = [], elements = Object.create(null);
            molecule.atoms.forEach(function (atom) {
                if (atom.element === 'H' && !p.labelHydrogens) { return; }
                if (!Object.prototype.hasOwnProperty.call(elements, atom.element)) {
                    elements[atom.element] = true;
                    runs.push({key: atom.element, text: atom.element, bold: false, italic: false});
                }
            });
            if (p.labels && runs.length) {
                if (req.discard) {
                    throw new Error('Element labels need a font with glyph outlines; choose a TrueType or OpenType font.');
                }
                if (!req.measured) { return JSON.stringify({measure: runs}); }
                runs.forEach(function (run) {
                    var m = req.measured[run.key];
                    if (!m || typeof m.path !== 'string' || !m.path
                            || ![m.w, m.h, m.d].every(Number.isFinite)) {
                        throw new Error('Element label measurements were incomplete.');
                    }
                });
            }
            var rad = Math.PI / 180;
            var q = engine.orientationFromEulerXYZ([p.pitch * rad, p.yaw * rad, p.roll * rad]);
            var center = [0, 0, 0], n = molecule.atoms.length;
            molecule.atoms.forEach(function (atom) {
                if (!Array.isArray(atom.position) || atom.position.length !== 3
                        || !atom.position.every(Number.isFinite)) { throw new Error('Invalid atom position.'); }
                for (var j = 0; j < 3; j++) { center[j] += atom.position[j]; }
            });
            center = center.map(function (v) { return v / n; });
            var halfX = 0, halfY = 0;
            molecule.atoms.forEach(function (atom) {
                var r = atom.radius === undefined ? engine.covalentRadii[atom.element] : atom.radius;
                if (!(r > 0) || !Number.isFinite(r)) { throw new Error('Unknown element radius: ' + atom.element); }
                r = Math.max(r * p.atomRadiusScale, 0.115);
                var xy = projected(atom.position.map(function (v, j) { return v - center[j]; }), q);
                halfX = Math.max(halfX, Math.abs(xy[0]) + r);
                halfY = Math.max(halfY, Math.abs(xy[1]) + r);
            });
            var svgScale = p.scale / 0.75, labelSize = p.labelSize / 0.75, padding = 12;
            if (p.labels && runs.length) {
                var labelPad = 2 * labelSize;
                runs.forEach(function (run) {
                    var m = req.measured[run.key];
                    labelPad = Math.max(labelPad, m.w * labelSize / 2,
                                        (m.h + m.d) * labelSize + labelSize * 0.3);
                });
                padding += labelPad;
            }
            var width = 2 * (halfX * svgScale + padding), height = 2 * (halfY * svgScale + padding);
            if (!Number.isFinite(width) || !Number.isFinite(height) || width > 2048 || height > 2048) {
                throw new Error('Projected molecule exceeds the 2048 SVG-unit size limit; reduce scale or coordinate extent.');
            }
            var canvasW = Math.max(200, Math.ceil(width)), canvasH = Math.max(200, Math.ceil(height));
            var options = {
                width: canvasW, height: canvasH, scale: svgScale, atomRadiusScale: p.atomRadiusScale,
                orientation: q, quality: 'export', renderMode: 'fast', lightType: 'directional', castShadows: false,
                lightAzimuth: p.lightAzimuth * rad, lightElevation: p.lightElevation * rad,
                shadingMode: p.shading === 'none' ? 'hatch' : p.shading,
                textureScale: p.textureScale, elementTextures: p.elementTextures,
                colorWash: p.colored, colorScheme: p.palette, labels: p.labels,
                labelSize: labelSize, labelColor: color, labelFont: 'sans-serif',
                labelBold: false, labelItalic: false, labelHydrogens: p.labelHydrogens,
                labelStrokeColor: '#ffffff', labelStrokeWidth: 4, labelMatchFill: false
            };
            if (p.shading === 'none') { options.shadingSize = 0; }
            var svg = engine.render(molecule, options);
            if (typeof svg !== 'string' || !/^<svg\b/.test(svg)) { throw new Error('Renderer returned invalid SVG.'); }
            // Only the exact upstream canvas rectangle is removed. White atom
            // and bond surfaces are necessary for occlusion and remain intact.
            svg = svg.replace('<rect width="100%" height="100%" fill="white"/>', '');
            svg = svg.replace(/^<svg\b[^>]*>/, function (tag) {
                return tag.replace(/\bwidth="[^"]*"/, 'width="' + width + '"')
                    .replace(/\bheight="[^"]*"/, 'height="' + height + '"')
                    .replace(/\bviewBox="[^"]*"/, 'viewBox="' + ((canvasW - width) / 2) + ' '
                             + ((canvasH - height) / 2) + ' ' + width + ' ' + height + '"');
            });
            if (p.labels && runs.length) {
                var centers = molecule.atoms.map(function (atom) {
                    var xy = projected(atom.position.map(function (v, j) { return v - center[j]; }), q);
                    return [canvasW / 2 + xy[0] * svgScale, canvasH / 2 - xy[1] * svgScale];
                });
                svg = outlinedLabels(svg, req.measured, centers);
            }
            svg = qtSvg(svg, canvasW, canvasH);
            if (/<text\b/.test(svg)) { throw new Error('Renderer returned unsupported text labels.'); }
            if (svg.length > 16 * 1024 * 1024) { throw new Error('Molecular SVG exceeds the output size limit.'); }
            var reply = veusz.svg(svg, {width: width * 0.75, height: height * 0.75, depth: 0});
            // Conservative UTF-16 accounting; never cache incomplete renders or errors.
            var bytes = 2 * (reply.length + key.length);
            if (bytes <= maxCacheBytes) {
                if (cache.has(key)) { cacheBytes -= cache.get(key).bytes; cache.delete(key); }
                while (cache.size >= 32 || cacheBytes + bytes > maxCacheBytes) {
                    var oldest = cache.keys().next().value;
                    cacheBytes -= cache.get(oldest).bytes; cache.delete(oldest);
                }
                cache.set(key, {reply: reply, bytes: bytes}); cacheBytes += bytes;
            }
            return reply;
        } catch (err) {
            return veusz.error('3D molecule could not draw this structure: ' + (err && err.message ? err.message : err));
        }
    });
}());
