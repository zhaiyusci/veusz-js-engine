/* Generated from src/wash.ts by npm run build. Edit TypeScript, not this file. */
var MolWash = (function (exports) {
    'use strict';

    /**
     * buildWash(scene, depthAt, project, scale, colorForElement, options?) -> SVG <g>.
     * options.fitCurves=false skips Bezier fitting for interactive preview.
     * scene is an array of spheres / cylinders in view coordinates; larger z is
     * nearer. project must be [ox + scale*x, oy - scale*y], with positive scale.
     * depthAt(shape, worldX, worldY) returns front z, or -Infinity outside.
     * Cylinders and white/null colors occlude but produce no fill. Exact depth
     * ties favor an uncolored surface; otherwise the earlier scene item wins.
     *
     * A 1 SVG-unit ownership grid supplies topology, NOT staircase geometry.
     * Dual-edge surface queries bisect crossings to 0.0001 SVG units; boundary
     * samples are adaptively refined and least-squares fitted to cubic Beziers
     * (0.012 fit tolerance, 0.003 sampling tolerance). Shared color interfaces
     * reuse identical curves in reverse, with shared refined three-way junctions.
     * Output is one evenodd path per normalized color using M/L/C/Z commands;
     * coordinates are rounded to 0.001 SVG units. No image, filter or dependency.
     *
     * Topology remains sampled: sub-cell islands, holes or multiple junctions
     * can be missed; this is not an analytic error guarantee for arbitrary depth
     * callbacks. Huge extents coarsen the grid to stay below 4M cells. Mask work
     * is bounded by clipped shape boxes; refinement checks candidate shapes at
     * boundary points. Memory is O(grid cells + boundary samples).
     */
    function buildWash(scene, depthAt, project, scale, colorForElement, options = {}) {
        var empty = '<g class="mol-wash"></g>';
        if (!Array.isArray(scene))
            throw new TypeError('scene must be an array');
        if (typeof depthAt !== 'function' || typeof project !== 'function' ||
            typeof colorForElement !== 'function')
            throw new TypeError('Expected callback functions');
        if (!(scale > 0) || !Number.isFinite(scale))
            throw new RangeError('scale must be finite and positive');
        var origin = project([0, 0, 0]);
        if (!valid2(origin))
            throw new RangeError('project must return finite coordinates');
        var shapes = [], colors = [''], colorIds = new Map();
        var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        scene.forEach(function (s) {
            if (!s || (s.kind !== 'sphere' && s.kind !== 'cylinder'))
                return;
            if (!(s.r > 0) || !Number.isFinite(s.r))
                return;
            var p, q, id = 0;
            if (s.kind === 'sphere') {
                if (!valid3(s.c))
                    return;
                p = q = project(s.c);
                var color = colorForElement(s.element);
                if (color != null && color !== '') {
                    color = String(color).trim().toLowerCase();
                    if (color === 'white' || color === '#fff')
                        color = '#ffffff';
                    if (!/^#[0-9a-f]{6}$/.test(color))
                        throw new TypeError('Element colors must be #rrggbb');
                    if (color !== '#ffffff') {
                        if (!colorIds.has(color)) {
                            colorIds.set(color, colors.length);
                            colors.push(color);
                        }
                        id = colorIds.get(color);
                    }
                }
            }
            else {
                if (!valid3(s.a) || !valid3(s.u) || !(s.length >= 0) || !Number.isFinite(s.length))
                    return;
                p = project(s.a);
                q = project([s.a[0] + s.u[0] * s.length, s.a[1] + s.u[1] * s.length,
                    s.a[2] + s.u[2] * s.length]);
            }
            if (!valid2(p) || !valid2(q))
                return;
            var r = s.r * scale;
            var b = [Math.min(p[0], q[0]) - r, Math.min(p[1], q[1]) - r,
                Math.max(p[0], q[0]) + r, Math.max(p[1], q[1]) + r];
            if (!b.every(Number.isFinite))
                throw new RangeError('Projected bounds overflow');
            shapes.push({ shape: s, bounds: b, label: id });
            if (s.kind === 'sphere') {
                minX = Math.min(minX, b[0]);
                minY = Math.min(minY, b[1]);
                maxX = Math.max(maxX, b[2]);
                maxY = Math.max(maxY, b[3]);
            }
        });
        if (maxX === -Infinity || colors.length === 1)
            return empty;
        var width = maxX - minX, height = maxY - minY;
        if (!Number.isFinite(width) || !Number.isFinite(height))
            throw new RangeError('Projected extent overflow');
        // Also bound skinny, extremely long viewports; padding covers outer edges.
        var step = Math.max(1, Math.sqrt(width) * Math.sqrt(height) / 1998, width / 3990000, height / 3990000);
        var nx = Math.ceil(width / step) + 2, ny = Math.ceil(height / step) + 2;
        while (nx * ny > 4000000) {
            step *= 1.1;
            nx = Math.ceil(width / step) + 2;
            ny = Math.ceil(height / step) + 2;
        }
        var x0 = minX - step, y0 = minY - step;
        var labels = new Uint32Array(nx * ny), depths = new Float64Array(nx * ny);
        depths.fill(-Infinity);
        shapes.forEach(function (item) {
            var b = item.bounds;
            var left = Math.max(0, Math.ceil((b[0] - x0) / step - 0.5));
            var right = Math.min(nx - 1, Math.floor((b[2] - x0) / step - 0.5));
            var top = Math.max(0, Math.ceil((b[1] - y0) / step - 0.5));
            var bottom = Math.min(ny - 1, Math.floor((b[3] - y0) / step - 0.5));
            for (var y = top; y <= bottom; y++) {
                var wy = (origin[1] - (y0 + (y + 0.5) * step)) / scale;
                for (var x = left; x <= right; x++) {
                    var wx = (x0 + (x + 0.5) * step - origin[0]) / scale;
                    var z = depthAt(item.shape, wx, wy), i = y * nx + x;
                    if (Number.isFinite(z) && (z > depths[i] || (z === depths[i] && item.label === 0))) {
                        depths[i] = z;
                        labels[i] = item.label;
                    }
                }
            }
        });
        // Directed lattice edges, with the owning pixel on their right side.
        // Direction codes: east=0, south=1, west=2, north=3.
        var stride = nx + 1, graphs = new Map();
        function edge(label, x, y, direction) {
            var graph = graphs.get(label);
            if (!graph) {
                graph = new Map();
                graphs.set(label, graph);
            }
            var v = y * stride + x;
            graph.set(v, (graph.get(v) || 0) | (1 << direction));
        }
        for (var y = 0; y < ny; y++) {
            for (var x = 0; x < nx; x++) {
                var i = y * nx + x, label = labels[i];
                if (!label)
                    continue;
                if (!y || labels[i - nx] !== label)
                    edge(label, x, y, 0);
                if (x === nx - 1 || labels[i + 1] !== label)
                    edge(label, x + 1, y, 1);
                if (y === ny - 1 || labels[i + nx] !== label)
                    edge(label, x + 1, y + 1, 2);
                if (!x || labels[i - 1] !== label)
                    edge(label, x, y + 1, 3);
            }
        }
        // The grid determines connectivity only. Coordinates come from the same
        // surface-depth oracle as the renderer, never from grid corners.
        function owner(p) {
            var best = -Infinity, label = 0;
            var wx = (p[0] - origin[0]) / scale, wy = (origin[1] - p[1]) / scale;
            for (var j = 0; j < shapes.length; j++) {
                var item = shapes[j], b = item.bounds;
                if (p[0] < b[0] || p[0] > b[2] || p[1] < b[1] || p[1] > b[3])
                    continue;
                var z = depthAt(item.shape, wx, wy);
                if (Number.isFinite(z) && (z > best || (z === best && item.label === 0))) {
                    best = z;
                    label = item.label;
                }
            }
            return label;
        }
        function bisect(a, b, label) {
            for (var k = 0; k < 32 && distance(a, b) > 0.0001; k++) {
                var m = mix(a, b, 0.5);
                if (owner(m) === label)
                    a = m;
                else
                    b = m;
            }
            return mix(a, b, 0.5);
        }
        var output = ['<g class="mol-wash" stroke="none">'];
        var delta = [1, stride, -1, -stride], crossings = new Map(), junctions = new Map(), fitted = new Map();
        function center(x, y) { return [x0 + (x + 0.5) * step, y0 + (y + 0.5) * step]; }
        function crossing(v, direction) {
            var end = v + delta[direction], key = Math.min(v, end) + ':' + Math.max(v, end);
            if (crossings.has(key))
                return crossings.get(key);
            var x = v % stride, y = Math.floor(v / stride), a, b;
            if (direction === 0) {
                a = center(x, y - 1);
                b = center(x, y);
            }
            if (direction === 1) {
                a = center(x - 1, y);
                b = center(x, y);
            }
            if (direction === 2) {
                a = center(x - 1, y - 1);
                b = center(x - 1, y);
            }
            if (direction === 3) {
                a = center(x - 1, y - 1);
                b = center(x, y - 1);
            }
            var la = owner(a), lb = owner(b), boundary = bisect(a, b, la);
            // A coarse dual edge can cross a third region between its two labels
            // (e.g. background at the tip of two tangent silhouettes). Its binary
            // crossing is then NOT on the requested interface; terminate at the
            // shared nearby junction instead of fitting a spurious hook into it.
            for (var probe = 1; probe < 8; probe++) {
                var middleLabel = owner(mix(a, b, probe / 8));
                if (middleLabel !== la && middleLabel !== lb) {
                    var ja = junction(v), jb = junction(end), nearest = ja || jb;
                    if (ja && jb && distance(jb.p, boundary) < distance(ja.p, boundary))
                        nearest = jb;
                    if (nearest)
                        boundary = nearest.p;
                    break;
                }
            }
            var point = { p: boundary, key: key, pair: [Math.min(la, lb), Math.max(la, lb)] };
            crossings.set(key, point);
            return point;
        }
        function junction(v) {
            if (junctions.has(v))
                return junctions.get(v);
            var x = v % stride, y = Math.floor(v / stride);
            var corners = [center(x - 1, y - 1), center(x, y - 1), center(x, y), center(x - 1, y)];
            var ls = corners.map(owner), tri = null;
            for (var a = 0; a < 4 && !tri; a++)
                for (var b = a + 1; b < 4 && !tri; b++)
                    for (var c = b + 1; c < 4; c++)
                        if (ls[a] !== ls[b] && ls[b] !== ls[c] && ls[a] !== ls[c]) {
                            tri = [corners[a], corners[b], corners[c]];
                            break;
                        }
            if (!tri) {
                junctions.set(v, null);
                return null;
            }
            // Refine the dual cell, retaining a subcell incident to three regions.
            // A triangle chosen from three corners need not enclose the junction:
            // its missing fourth corner can hide an intervening silhouette arc.
            var cells = [[corners[0][0], corners[0][1], step]];
            for (var it = 0; it < 16 && cells[0][2] > 0.0001; it++) {
                var found = [];
                cells.forEach(function (cell) {
                    var bx = cell[0] - cell[2] * 1.5, by = cell[1] - cell[2] * 1.5, h = cell[2] / 4, samples = [];
                    for (var yy = 0; yy <= 16; yy++)
                        for (var xx = 0; xx <= 16; xx++)
                            samples.push(owner([bx + xx * h, by + yy * h]));
                    for (var yy = 0; yy < 16; yy++)
                        for (var xx = 0; xx < 16; xx++) {
                            var at = yy * 17 + xx;
                            var ids = new Set([samples[at], samples[at + 1], samples[at + 17], samples[at + 18]]);
                            if (ids.size >= 3)
                                found.push([bx + xx * h, by + yy * h, h]);
                        }
                });
                if (!found.length)
                    break;
                // Recenter the expanded search on the closest candidate. A thin wedge
                // can put three labels in a cell whose actual junction is just outside.
                found.sort(function (a, b) {
                    var target = [x0 + x * step, y0 + y * step];
                    return distance([a[0] + a[2] / 2, a[1] + a[2] / 2], target) - distance([b[0] + b[2] / 2, b[1] + b[2] / 2], target);
                });
                cells = found.slice(0, 1);
            }
            var cell = cells[0], p = [cell[0] + cell[2] / 2, cell[1] + cell[2] / 2];
            var result = { p: p, key: 'j' + v, junction: true };
            junctions.set(v, result);
            return result;
        }
        function refine(a, b, pair, depth, result) {
            var len = distance(a, b);
            if (len < 0.025 || depth > 12) {
                result.push(b);
                return;
            }
            var m = mix(a, b, 0.5), n = [(b[1] - a[1]) / len, (a[0] - b[0]) / len];
            var span = Math.max(0.02, len * 0.6), lo, hi, l, h;
            for (var k = 0; k < 5; k++) {
                lo = add(m, n, -span);
                hi = add(m, n, span);
                l = owner(lo);
                h = owner(hi);
                if (l !== h && pair.indexOf(l) >= 0 && pair.indexOf(h) >= 0)
                    break;
                span *= 0.5;
            }
            var thirdRegion = false;
            if (l !== h && pair.indexOf(l) >= 0 && pair.indexOf(h) >= 0) {
                for (var probe = 1; probe < 8; probe++)
                    if (pair.indexOf(owner(mix(lo, hi, probe / 8))) < 0)
                        thirdRegion = true;
            }
            if (thirdRegion || l === h || pair.indexOf(l) < 0 || pair.indexOf(h) < 0) {
                // Near a three-way corner the third region may occupy one side of a
                // wide normal bracket. Search for the requested pair, not its silhouette.
                var previous = add(m, n, -len), previousLabel = owner(previous), best = Infinity, bracket = null;
                for (var scan = 1; scan <= 128; scan++) {
                    var candidate = add(m, n, -len + 2 * len * scan / 128), candidateLabel = owner(candidate);
                    if (candidateLabel !== previousLabel && pair.indexOf(candidateLabel) >= 0 && pair.indexOf(previousLabel) >= 0) {
                        var score = distance(m, mix(previous, candidate, 0.5));
                        if (score < best) {
                            best = score;
                            bracket = [previous, candidate, previousLabel];
                        }
                    }
                    previous = candidate;
                    previousLabel = candidateLabel;
                }
                if (!bracket) {
                    result.push(b);
                    return;
                }
                lo = bracket[0];
                hi = bracket[1];
                l = bracket[2];
            }
            var q = bisect(lo, hi, l);
            if (distance(m, q) > 0.003 || len > 0.5) {
                refine(a, q, pair, depth + 1, result);
                refine(q, b, pair, depth + 1, result);
            }
            else
                result.push(b);
        }
        function chain(nodes, pair) {
            var reverse = nodes[0].key > nodes[nodes.length - 1].key;
            if (reverse)
                nodes = nodes.slice().reverse();
            var key = nodes.map(function (p) { return p.key; }).join('/');
            var curves = fitted.get(key);
            if (!curves) {
                var samples = [nodes[0].p];
                for (var j = 1; j < nodes.length; j++)
                    refine(nodes[j - 1].p, nodes[j].p, pair, 0, samples);
                // Preview preserves the same refined boundary and shared interfaces,
                // but skips fitting entirely; export retains the compact cubic geometry.
                curves = options.fitCurves === false
                    ? samples.slice(1).map(function (p, i) { return [samples[i], p]; })
                    : fitContour(samples, 0.012);
                fitted.set(key, curves);
            }
            if (reverse)
                curves = curves.slice().reverse().map(function (c) { return c.slice().reverse(); });
            return curves;
        }
        function contour(nodes) {
            var cuts = [];
            for (var k = 0; k < nodes.length; k++)
                if (nodes[k].junction)
                    cuts.push(k);
            // Closed two-label curves use a deterministic seam and antipodal split;
            // the reverse walk then reuses precisely the same fitted cubic segments.
            if (!cuts.length) {
                var first = 0;
                for (var k = 1; k < nodes.length; k++)
                    if (nodes[k].key < nodes[first].key)
                        first = k;
                var far = first;
                for (var k = 0; k < nodes.length; k++)
                    if (distance(nodes[k].p, nodes[first].p) > distance(nodes[far].p, nodes[first].p))
                        far = k;
                cuts = [first, far].sort(function (a, b) { return a - b; });
            }
            var d = 'M' + coord(nodes[cuts[0]].p);
            for (var k = 0; k < cuts.length; k++) {
                var run = [nodes[cuts[k]]], at = (cuts[k] + 1) % nodes.length, end = cuts[(k + 1) % cuts.length];
                while (at !== end) {
                    run.push(nodes[at]);
                    at = (at + 1) % nodes.length;
                }
                run.push(nodes[end]);
                var pair = run.find(function (p) { return p.pair; }).pair;
                chain(run, pair).forEach(function (c) {
                    d += c.length === 2 ? 'L' + coord(c[1]) : 'C' + coord(c[1]) + ' ' + coord(c[2]) + ' ' + coord(c[3]);
                });
            }
            return d + 'Z';
        }
        graphs.forEach(function (graph, label) {
            var loops = [];
            graph.forEach(function (_, start) {
                while (graph.get(start)) {
                    var mask = graph.get(start), direction = 0;
                    while (!(mask & (1 << direction)))
                        direction++;
                    var v = start, points = [];
                    do {
                        var jp = junction(v);
                        if (jp)
                            points.push(jp);
                        points.push(crossing(v, direction));
                        var bits = graph.get(v);
                        graph.set(v, bits & ~(1 << direction));
                        var next = v + delta[direction];
                        if (next === start)
                            break;
                        var available = graph.get(next) || 0;
                        // At diagonal contact choose a right turn, keeping components
                        // separate instead of creating a self-crossing figure-eight.
                        var choices = [(direction + 1) % 4, direction, (direction + 3) % 4, (direction + 2) % 4];
                        var nextDirection = -1;
                        for (var k = 0; k < 4; k++) {
                            if (available & (1 << choices[k])) {
                                nextDirection = choices[k];
                                break;
                            }
                        }
                        if (nextDirection < 0)
                            throw new Error('Open wash contour');
                        v = next;
                        direction = nextDirection;
                    } while (true);
                    if (points.length >= 3)
                        loops.push(contour(points));
                }
            });
            if (loops.length)
                output.push('<path fill="' + colors[label] + '" fill-rule="evenodd" d="' + loops.join('') + '"/>');
        });
        output.push('</g>');
        return output.join('');
    }
    function coord(p) { return format(p[0]) + ' ' + format(p[1]); }
    function distance(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1]); }
    function mix(a, b, t) { return [a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t]; }
    function add(a, b, s) { return [a[0] + b[0] * s, a[1] + b[1] * s]; }
    function unit(a, b) { var d = distance(a, b); return d ? [(b[0] - a[0]) / d, (b[1] - a[1]) / d] : [1, 0]; }
    function dot(a, b) { return a[0] * b[0] + a[1] * b[1]; }
    function bezier(c, t) { var a = mix(c[0], c[1], t), b = mix(c[1], c[2], t), d = mix(c[2], c[3], t); return mix(mix(a, b, t), mix(b, d, t), t); }
    // Schneider-style least-squares cubic fitting, with chord-length parameters,
    // Newton reparameterization and recursive maximum-error subdivision. The
    // samples have already been refined against the depth oracle to 0.003 SVG.
    function fitContour(input, tolerance) {
        var p = input.filter(function (q, i) { return !i || i === input.length - 1 || distance(q, input[i - 1]) > 0.0002; });
        while (p.length > 2 && distance(p[p.length - 2], p[p.length - 1]) <= 0.0002)
            p.splice(p.length - 2, 1);
        var result = [];
        if (p.length < 2)
            return result;
        function fit(lo, hi, left, right, depth) {
            var count = hi - lo, length = 0, u = [0];
            for (var i = lo + 1; i <= hi; i++) {
                length += distance(p[i - 1], p[i]);
                u.push(length);
            }
            if (count === 1) {
                result.push([p[lo], p[hi]]);
                return;
            }
            u = u.map(function (v) { return v / length; });
            var split = lo + Math.floor(count / 2), curve;
            for (var iteration = 0; iteration < 5; iteration++) {
                var c00 = 0, c01 = 0, c11 = 0, x0 = 0, x1 = 0;
                for (var j = 0; j <= count; j++) {
                    var t = u[j], s = 1 - t, b0 = s * s * s, b1 = 3 * t * s * s, b2 = 3 * t * t * s, b3 = t * t * t;
                    var a = [left[0] * b1, left[1] * b1], b = [right[0] * b2, right[1] * b2];
                    var r = [p[lo + j][0] - p[lo][0] * (b0 + b1) - p[hi][0] * (b2 + b3),
                        p[lo + j][1] - p[lo][1] * (b0 + b1) - p[hi][1] * (b2 + b3)];
                    c00 += dot(a, a);
                    c01 += dot(a, b);
                    c11 += dot(b, b);
                    x0 += dot(a, r);
                    x1 += dot(b, r);
                }
                var det = c00 * c11 - c01 * c01;
                var alpha = det ? (x0 * c11 - x1 * c01) / det : 0;
                var beta = det ? (c00 * x1 - c01 * x0) / det : 0;
                if (alpha < length * 1e-6 || beta < length * 1e-6 || alpha > length || beta > length)
                    alpha = beta = distance(p[lo], p[hi]) / 3;
                curve = [p[lo], add(p[lo], left, alpha), add(p[hi], right, beta), p[hi]];
                var error = 0;
                for (var j = 1; j < count; j++) {
                    var err = distance(bezier(curve, u[j]), p[lo + j]);
                    if (err > error) {
                        error = err;
                        split = lo + j;
                    }
                }
                // Also test between sample parameters: this prevents an interpolating
                // cubic from overshooting a short, sharply turning boundary segment.
                for (var j = 0; j < count; j++) {
                    var q = bezier(curve, (u[j] + u[j + 1]) / 2), a = p[lo + j], b = p[lo + j + 1];
                    var dx = b[0] - a[0], dy = b[1] - a[1], dd = dx * dx + dy * dy;
                    var f = dd ? Math.max(0, Math.min(1, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / dd)) : 0;
                    var err = distance(q, mix(a, b, f));
                    if (err > error) {
                        error = err;
                        split = Math.max(lo + 1, Math.min(hi - 1, lo + j));
                    }
                }
                if (error <= tolerance) {
                    result.push(curve);
                    return;
                }
                if (iteration === 4 || error > tolerance * 8)
                    break;
                var updated = [0], valid = true;
                for (var j = 1; j < count; j++) {
                    var t = u[j], q = bezier(curve, t), s = 1 - t;
                    var d = [0, 0], secondDerivative = [0, 0];
                    for (var axis = 0; axis < 2; axis++) {
                        d[axis] = 3 * (s * s * (curve[1][axis] - curve[0][axis]) + 2 * s * t * (curve[2][axis] - curve[1][axis]) + t * t * (curve[3][axis] - curve[2][axis]));
                        secondDerivative[axis] = 6 * (s * (curve[2][axis] - 2 * curve[1][axis] + curve[0][axis]) + t * (curve[3][axis] - 2 * curve[2][axis] + curve[1][axis]));
                    }
                    var r = [q[0] - p[lo + j][0], q[1] - p[lo + j][1]], denominator = dot(d, d) + dot(r, secondDerivative);
                    var next = denominator ? t - dot(r, d) / denominator : t;
                    if (!(next > updated[j - 1] && next < 1))
                        valid = false;
                    updated.push(next);
                }
                if (!valid)
                    break;
                updated.push(1);
                u = updated;
            }
            if (depth > 32) {
                for (var i = lo + 1; i <= hi; i++)
                    result.push([p[i - 1], p[i]]);
                return;
            }
            var tangent = unit(p[split + 1], p[split - 1]);
            fit(lo, split, left, tangent, depth + 1);
            fit(split, hi, [-tangent[0], -tangent[1]], right, depth + 1);
        }
        // Preserve actual corners (e.g. flat cylinder caps) instead of forcing a
        // common tangent there. Tiny bisection noise is below this angle threshold.
        var cuts = [0];
        for (var i = 1; i < p.length - 1; i++) {
            var a = i - 1, b = i + 1;
            while (a > 0 && distance(p[a], p[i]) < 0.04)
                a--;
            while (b < p.length - 1 && distance(p[b], p[i]) < 0.04)
                b++;
            if (dot(unit(p[a], p[i]), unit(p[i], p[b])) < 0.8 && i - cuts[cuts.length - 1] > 1)
                cuts.push(i);
        }
        cuts.push(p.length - 1);
        for (var i = 1; i < cuts.length; i++) {
            var lo = cuts[i - 1], hi = cuts[i];
            fit(lo, hi, unit(p[lo], p[lo + 1]), unit(p[hi], p[hi - 1]), 0);
        }
        return result;
    }
    function valid2(p) { return p && Number.isFinite(p[0]) && Number.isFinite(p[1]); }
    function valid3(p) { return valid2(p) && Number.isFinite(p[2]); }
    function format(n) { return String(Math.round(n * 1000) / 1000); }

    exports.buildWash = buildWash;
    exports.fitContour = fitContour;

    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });

    return exports;

})({});
if (typeof module !== 'undefined' && module.exports) module.exports = MolWash;
