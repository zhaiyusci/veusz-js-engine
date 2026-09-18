/* Copyright (c) 2026 veusz-js-engine contributors.
 * SPDX-License-Identifier: Apache-2.0
 * Licensed under the Apache License, Version 2.0 (see repository LICENSE).
 * http://www.apache.org/licenses/LICENSE-2.0
 * Distributed AS IS, without warranties or conditions of any kind.
 * Feature-owned no-browser adapter for the unmodified SmilesDrawer 2.4.1.
 * Load this file BEFORE smiles-drawer.js: upstream exports through window.
 * Only SVG construction and a metric-only canvas are implemented, not a DOM.
 * smilesToSvg(JSON) returns {measure:[...]} or {svg,width,height,...}.
 * Supply platform measure_text_runs results as `measured` on the second call.
 * Glyph paths are in 1000 units/em; numeric SVG geometry is CSS pixels.
 * QtSvg lacks portable SVG masks/CSS transforms: subtract the upstream mask
 * circles from bond geometry instead. No opaque background or lost labels.
 */
(function (global) {
    'use strict';
    if (global.smilesToSvg) return;
    var active = null;
    var NS = 'http://www.w3.org/2000/svg';
    function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function Node(name, text) { this.name = name; this.attributes = Object.create(null); this.children = []; this.style = {}; this.text = text || ''; }
    Node.prototype.setAttribute = function (k, v) { this.attributes[k] = String(v); };
    Node.prototype.setAttributeNS = function (_, k, v) { this.setAttribute(k, v); };
    Node.prototype.getAttribute = function (k) { return this.attributes[k] === undefined ? null : this.attributes[k]; };
    Node.prototype.appendChild = function (n) { this.children.push(n); return n; };
    Node.prototype.removeChild = function (n) { var i = this.children.indexOf(n); if (i >= 0) this.children.splice(i, 1); return n; };
    Object.defineProperty(Node.prototype, 'firstChild', {get: function () { return this.children[0] || null; }});
    Object.defineProperty(Node.prototype, 'textContent', {get: function () { return this.text + this.children.map(function (c) { return c.textContent; }).join(''); }, set: function (s) { this.text = String(s); this.children = []; }});
    Object.defineProperty(Node.prototype, 'outerHTML', {get: function () { return serialize(this); }});
    function serialize(n) {
        if (n.name === '#text') return esc(n.text);
        var attrs = Object.assign({}, n.attributes);
        // The shared platform strips stroke-width attributes for MathJax;
        // style keeps the deliberate chemical bond thickness intact.
        if (attrs['stroke-width']) { attrs.style = (attrs.style ? attrs.style + ';' : '') + 'stroke-width:' + attrs['stroke-width']; delete attrs['stroke-width']; }
        ['fill', 'stroke'].forEach(function (k) { if (attrs[k] === '#000000') attrs[k] = '#000'; });
        var a = Object.keys(attrs).map(function (k) { return ' ' + k + '="' + esc(attrs[k]) + '"'; }).join('');
        return '<' + n.name + a + '>' + esc(n.text) + n.children.map(serialize).join('') + '</' + n.name + '>';
    }
    function Svg() { Node.call(this, 'svg'); }
    Svg.prototype = Object.create(Node.prototype); Svg.prototype.constructor = Svg;
    function metric(text) {
        var key = 'smiles:' + text;
        active.requests[key] = {key: key, text: text, bold: false, italic: false};
        var m = active.measured[key];
        if (m) {
            if (!Number.isFinite(m.w) || !Number.isFinite(m.h) || !Number.isFinite(m.d) || m.w < 0 || m.h < 0 || m.d < 0 || typeof m.path !== 'string' || (text.trim() && !m.path.trim())) throw Error('SMILES: invalid or missing text outline: ' + text);
            return m;
        }
        active.missing = true;
        return {w: Array.from(text).length * 0.68, h: 0.75, d: 0.22, path: ''};
    }
    var document = {
        createElementNS: function (ns, name) { if (ns !== NS) throw Error('SMILES: unsupported namespace'); return name === 'svg' ? new Svg() : new Node(name); },
        createTextNode: function (s) { return new Node('#text', String(s)); },
        createElement: function (name) {
            if (name !== 'canvas') throw Error('SMILES: unsupported DOM element ' + name);
            return {getContext: function (kind) {
                if (kind !== '2d') return null;
                return {font: '', measureText: function (text) {
                    // Upstream measures at 16pt, then rescales by fontSize/16.
                    var m = metric(String(text)), em = 16 * 4 / 3;
                    return {actualBoundingBoxLeft: 0, actualBoundingBoxRight: m.w * em, actualBoundingBoxAscent: m.h * em, actualBoundingBoxDescent: m.d * em};
                }};
            }};
        }
    };
    global.document = document;
    global.SVGSVGElement = Svg;
    // Intentionally not window=globalThis: expose only upstream's export gate.
    global.window = {document: document};

    function clone(n) { var x = new Node(n.name); Object.keys(n.attributes).forEach(function (k) { x.attributes[k] = n.attributes[k]; }); return x; }
    function number(n, key) { var v = Number(n.attributes[key]); if (!Number.isFinite(v)) throw Error('SMILES: non-finite ' + key); return v; }
    function circle(n) { return {x: number(n, 'cx'), y: number(n, 'cy'), r: number(n, 'r')}; }
    function outsideLine(n, masks) {
        var x = number(n, 'x1'), y = number(n, 'y1'), dx = number(n, 'x2') - x, dy = number(n, 'y2') - y;
        var length = Math.hypot(dx, dy), intervals = [[0, 1]], half = Number(n.attributes['stroke-width'] || 1) / 2;
        if (length < 1e-10) return []; // zero-width first dash of a hashed wedge
        masks.forEach(function (c) {
            var vx = x - c.x, vy = y - c.y, rr = c.r + half;
            var a = length * length, b = 2 * (vx * dx + vy * dy), d = b * b - 4 * a * (vx * vx + vy * vy - rr * rr);
            if (d <= 0) return;
            var lo = (-b - Math.sqrt(d)) / (2 * a), hi = (-b + Math.sqrt(d)) / (2 * a), next = [];
            intervals.forEach(function (p) { if (hi <= p[0] || lo >= p[1]) next.push(p); else { if (lo > p[0]) next.push([p[0], lo]); if (hi < p[1]) next.push([hi, p[1]]); } }); intervals = next;
        });
        return intervals.map(function (p) {
            var out = clone(n); out.setAttribute('x1', x + p[0] * dx); out.setAttribute('y1', y + p[0] * dy); out.setAttribute('x2', x + p[1] * dx); out.setAttribute('y2', y + p[1] * dy);
            if (n.attributes['stroke-dasharray']) out.setAttribute('stroke-dashoffset', -(Number(n.attributes['stroke-dashoffset'] || 0) + p[0] * length));
            return out;
        });
    }
    // Difference of a convex wedge polygon and a circular hole. Circumscribed
    // 64-gon error <0.13%; output disjoint convex pieces, no Qt clipping needed.
    function halfplane(poly, a, b, inside) {
        var out = [], prev = poly[poly.length - 1];
        function side(p) { return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]); }
        var ps = side(prev);
        poly.forEach(function (p) { var s = side(p), pin = inside ? ps >= 0 : ps <= 0, cin = inside ? s >= 0 : s <= 0;
            if (pin !== cin) { var t = ps / (ps - s); out.push([prev[0] + t * (p[0] - prev[0]), prev[1] + t * (p[1] - prev[1])]); }
            if (cin) out.push(p); prev = p; ps = s;
        }); return out;
    }
    function outsidePolygon(n, masks) {
        var parts = [n.attributes.points.trim().split(/\s+/).map(function (s) { return s.split(',').map(Number); })];
        masks.forEach(function (c) {
            var next = [], count = 64, radius = c.r / Math.cos(Math.PI / count), boundary = [];
            for (var i = 0; i < count; i++) { var a = i * 2 * Math.PI / count; boundary.push([c.x + radius * Math.cos(a), c.y + radius * Math.sin(a)]); }
            parts.forEach(function (p) {
                var xs = p.map(function (v) { return v[0]; }), ys = p.map(function (v) { return v[1]; });
                if (Math.max.apply(null, xs) < c.x - radius || Math.min.apply(null, xs) > c.x + radius || Math.max.apply(null, ys) < c.y - radius || Math.min.apply(null, ys) > c.y + radius) { next.push(p); return; }
                for (var j = 0; j < count && p.length >= 3; j++) { var a = boundary[j], b = boundary[(j + 1) % count], piece = halfplane(p, a, b, false); if (piece.length >= 3) next.push(piece); p = halfplane(p, a, b, true); }
            }); parts = next;
        });
        if (!parts.length) return [];
        // One compound path avoids antialias seams between adjacent pieces.
        var out = clone(n); out.name = 'path'; delete out.attributes.points;
        out.setAttribute('d', parts.map(function (p) { return 'M' + p.map(function (v) { return v.join(' '); }).join('L') + 'Z'; }).join(''));
        out.setAttribute('fill-rule', 'nonzero');
        return [out];
    }
    function unmask(wrapper) {
        var masks = wrapper.maskElements.map(function (n) { if (n.name !== 'circle') throw Error('SMILES: unsupported upstream mask shape ' + n.name); return circle(n); });
        var paths = [];
        wrapper.paths.forEach(function (n) {
            if (!masks.length) { paths.push(n); return; }
            if (n.name === 'line') paths.push.apply(paths, outsideLine(n, masks));
            else if (n.name === 'polygon') paths.push.apply(paths, outsidePolygon(n, masks));
            else if (n.name === 'circle') {
                var c = circle(n), half = Number(n.attributes['stroke-width'] || 1) / 2;
                var intersects = masks.some(function (m) { var d = Math.hypot(c.x - m.x, c.y - m.y); return d + c.r >= m.r && Math.abs(d - c.r) < m.r + half; });
                if (!intersects) { if (!masks.some(function (m) { return Math.hypot(c.x - m.x, c.y - m.y) + c.r < m.r; })) paths.push(n); return; }
                // Rare ring/text intersection: flatten circumference at <=0.01px
                // sagitta, preserving stroke and dash phase on each segment.
                var count = Math.max(96, Math.ceil(Math.PI * Math.sqrt(c.r / 0.02)));
                for (var i = 0; i < count; i++) { var a = i * Math.PI * 2 / count, b = (i + 1) * Math.PI * 2 / count, line = clone(n); line.name = 'line'; delete line.attributes.cx; delete line.attributes.cy; delete line.attributes.r;
                    line.setAttribute('x1', c.x + c.r * Math.cos(a)); line.setAttribute('y1', c.y + c.r * Math.sin(a)); line.setAttribute('x2', c.x + c.r * Math.cos(b)); line.setAttribute('y2', c.y + c.r * Math.sin(b)); paths.push.apply(paths, outsideLine(line, masks)); }
            } else throw Error('SMILES: unsupported masked bond geometry ' + n.name);
        });
        return paths;
    }
    function labels(wrapper, em) {
        var output = [];
        wrapper.vertices.forEach(function (g) {
            if (g.name !== 'g') { output.push(g); return; }
            var t = g.children[0];
            if (!t || t.name !== 'text') throw Error('SMILES: unexpected label structure');
            var match = /translateX\(([-+\d.eE]+)px\) translateY\(([-+\d.eE]+)px\)/.exec(g.attributes.style || '');
            if (!match) throw Error('SMILES: unexpected upstream label transform');
            var gx = Number(match[1]), gy = Number(match[2]), direction = t.attributes['data-direction'];
            var runs = t.children.map(function (s) { return {text: s.textContent, color: s.attributes.fill, m: metric(s.textContent)}; });
            var total = runs.reduce(function (sum, r) { return sum + r.m.w * em; }, 0), cursor = direction === 'left' ? -total : 0;
            runs.forEach(function (r, i) {
                var vertical = direction === 'up' || direction === 'down';
                var x = gx + (vertical ? 0 : cursor);
                var y = gy + (vertical ? (direction === 'up' ? -1 : 1) * i * 0.9 * em + (r.m.h - r.m.d) * em / 2 : 0.36 * em);
                var p = new Node('path'); p.setAttribute('fill', r.color); p.setAttribute('d', r.m.path);
                p.setAttribute('transform', 'translate(' + x + ' ' + y + ') scale(' + em / 1000 + ')'); output.push(p);
                wrapper.minX = Math.min(wrapper.minX, x - 0.15 * em); wrapper.maxX = Math.max(wrapper.maxX, x + r.m.w * em + 0.15 * em);
                wrapper.minY = Math.min(wrapper.minY, y - r.m.h * em); wrapper.maxY = Math.max(wrapper.maxY, y + r.m.d * em);
                cursor += r.m.w * em;
            });
        }); return output;
    }
    global.smilesToSvg = function (json) {
        var request;
        try { request = JSON.parse(json); } catch (_) { throw Error('SMILES: expected a JSON request'); }
        if (!request || typeof request.smiles !== 'string' || !request.smiles.trim()) throw Error('SMILES: source must be a nonempty string');
        if (request.smiles.length > 4096) throw Error('SMILES: source exceeds 4096 characters');
        var lib = global.window.SmilesDrawer || global.SmilesDrawer;
        if (!lib || lib.Version !== '2.4.1') throw Error('SMILES: load headless.js before the official SmilesDrawer 2.4.1 bundle');
        var opts = {scale: 1, padding: 10, compactDrawing: false, debug: false};
        var allowed = {bondLength: [8, 100], bondThickness: [0.1, 5], bondSpacing: [0.5, 20], fontSizeLarge: [4, 40], fontSizeSmall: [1, 20], padding: [0, 100], scale: [0.05, 20], width: [1, 10000], height: [1, 10000]};
        Object.keys(request.options || {}).forEach(function (k) {
            var v = request.options[k];
            if (allowed[k]) { if (typeof v !== 'number' || !Number.isFinite(v) || v < allowed[k][0] || v > allowed[k][1]) throw Error('SMILES: invalid option ' + k); opts[k] = v; }
            else if (['terminalCarbons', 'explicitHydrogens', 'isomeric', 'compactDrawing'].indexOf(k) >= 0 && typeof v === 'boolean') opts[k] = v;
            else throw Error('SMILES: unsupported option ' + k);
        });
        var theme = request.theme || 'light';
        if (theme !== 'light' && theme !== 'dark') throw Error('SMILES: theme must be light or dark');
        active = {requests: Object.create(null), measured: request.measured || {}, missing: false};
        try {
            // Direct strict parser: never clean, truncate or silently fix source.
            var tree = lib.Parser.parse(request.smiles);
            var drawer = new lib.SvgDrawer(opts);
            if (request.color !== undefined) {
                if (typeof request.color !== 'string' || !/^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$/.test(request.color)) throw Error('SMILES: color must be #RGB or #RRGGBB');
                Object.keys(drawer.opts.themes[theme]).forEach(function (k) { if (k !== 'BACKGROUND') drawer.opts.themes[theme][k] = request.color; });
            }
            // Guard BEFORE expensive layout by counting parsed atoms.
            var count = 0, rings = Object.create(null);
            function countTree(t) {
                if (!t || typeof t !== 'object') return;
                if (t.atom !== undefined && ++count > 256) throw Error('SMILES: molecule exceeds 256 atoms');
                (t.ringbonds || []).forEach(function (r) {
                    var id = String(r.id);
                    if (rings[id] === t) throw Error('SMILES: ring closure cannot connect an atom to itself');
                    if (rings[id]) delete rings[id]; else rings[id] = t;
                });
                (t.branches || []).forEach(countTree);
                if (t.next) countTree(t.next);
            }
            countTree(tree);
            if (Object.keys(rings).length) throw Error('SMILES: unmatched ring closure ' + Object.keys(rings).join(', '));
            var svg = drawer.draw(tree, null, theme), w = drawer.svgWrapper;
            var labelNodes = labels(w, drawer.opts.fontSizeLarge * 4 / 3);
            if (active.missing) return JSON.stringify({measure: Object.keys(active.requests).map(function (k) { return active.requests[k]; })});
            var paths = unmask(w), defs = new Node('defs'), bonds = new Node('g'), atoms = new Node('g');
            w.gradients.forEach(function (n) { defs.appendChild(n); }); paths.forEach(function (n) { bonds.appendChild(n); }); labelNodes.forEach(function (n) { atoms.appendChild(n); });
            svg.children = [defs, bonds, atoms];
            // Include stroke extents even if the caller requests zero padding.
            var strokePad = drawer.opts.bondThickness / 2;
            w.minX -= strokePad; w.minY -= strokePad; w.maxX += strokePad; w.maxY += strokePad;
            w.updateViewbox(drawer.opts.scale);
            var box = svg.attributes.viewBox.split(/\s+/).map(Number), width = box[2] * drawer.opts.scale, height = box[3] * drawer.opts.scale;
            // Explicit viewport sizes are optional; a single dimension keeps
            // the natural aspect ratio. Both dimensions use SVG meet fitting.
            var requested = request.options || {};
            if (requested.width !== undefined && requested.height !== undefined) { width = requested.width; height = requested.height; }
            else if (requested.width !== undefined) { height *= requested.width / width; width = requested.width; }
            else if (requested.height !== undefined) { width *= requested.height / height; height = requested.height; }
            if (!box.every(Number.isFinite) || !(width > 0 && height > 0)) throw Error('SMILES: invalid drawing bounds');
            svg.setAttribute('width', width); svg.setAttribute('height', height);
            // Stable IDs make repeated renders/cache comparisons deterministic.
            var markup = serialize(svg).split(w.uid + '-').join('smiles-');
            return JSON.stringify({svg: markup, width: width, height: height, viewBox: box, engine: 'SmilesDrawer', version: lib.Version, atomCount: drawer.preprocessor.graph.vertices.length, units: 'px', fontSize: drawer.opts.fontSizeLarge * 4 / 3, maskMode: 'geometry'});
        } catch (e) { var message = e && e.message ? e.message : String(e); throw Error(message.indexOf('SMILES: ') === 0 ? message : 'SMILES: ' + message); }
        finally { active = null; }
    };
})(globalThis);
