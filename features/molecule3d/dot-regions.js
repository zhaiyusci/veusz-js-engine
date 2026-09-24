/* Generated from src/dot-regions.ts by npm run build. Edit TypeScript, not this file. */
var MolDotRegions = (function (exports) {
    'use strict';

    const TAU = 2 * Math.PI, EPS = Number.EPSILON;
    function overlaps(a, b) {
        return a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3];
    }
    function box$1(edges) {
        const b = [Infinity, Infinity, -Infinity, -Infinity];
        for (const e of edges)
            for (let k = 0; k < 4; k++)
                b[k] = k < 2 ? Math.min(b[k], e.bounds[k]) : Math.max(b[k], e.bounds[k]);
        return b;
    }
    function index(edges) {
        const bounds = box$1(edges);
        if (edges.length <= 12)
            return { bounds, edges };
        const axis = bounds[2] - bounds[0] >= bounds[3] - bounds[1] ? 0 : 1;
        edges.sort((a, b) => (a.bounds[axis] + a.bounds[axis + 2]) - (b.bounds[axis] + b.bounds[axis + 2]));
        const half = edges.length >>> 1;
        return { bounds, left: index(edges.slice(0, half)), right: index(edges.slice(half)) };
    }
    function visit(node, bounds, fn) {
        if (!overlaps(node.bounds, bounds))
            return;
        if (node.edges) {
            for (const e of node.edges)
                if (overlaps(e.bounds, bounds))
                    fn(e);
        }
        else {
            visit(node.left, bounds, fn);
            visit(node.right, bounds, fn);
        }
    }
    function intervals(cuts, at, contains, accept) {
        cuts.sort((a, b) => a - b);
        const result = [];
        for (let i = 1; i < cuts.length; i++) {
            const a = cuts[i - 1], b = cuts[i];
            if (!(b > a))
                continue;
            const midpoint = a + (b - a) / 2;
            if (accept && !accept(midpoint))
                continue;
            const p = at(midpoint);
            if (!contains(p[0], p[1]))
                continue;
            const last = result[result.length - 1];
            // Merge only exactly adjacent accepted bins, never across a small hole.
            if (last && last[1] === a)
                last[1] = b;
            else
                result.push([a, b]);
        }
        return result;
    }
    function valid(p) { return Number.isFinite(p[0]) && Number.isFinite(p[1]); }
    /** The edges must describe complete closed contours. Orientation is irrelevant.
     * Bounds are [minX,minY,maxX,maxY]; a supplied box is conservatively enlarged.
     * Boundaries belong to the region, including a line coincident with an edge.
     */
    function createRegion(input, bounds) {
        const edges = [];
        for (const e of input) {
            if (!valid(e.p) || !valid(e.q))
                throw new Error('Non-finite region edge');
            const p = e.p.slice(0, 2), q = e.q.slice(0, 2);
            if (p[0] === q[0] && p[1] === q[1])
                continue;
            edges.push({ p, q, dx: q[0] - p[0], dy: q[1] - p[1], bounds: [Math.min(p[0], q[0]), Math.min(p[1], q[1]), Math.max(p[0], q[0]), Math.max(p[1], q[1])] });
        }
        const root = index(edges), regionBounds = root.bounds.slice();
        if (bounds && bounds.length >= 4 && bounds.slice(0, 4).every(Number.isFinite)) {
            for (let k = 0; k < 4; k++)
                regionBounds[k] = k < 2 ? Math.min(regionBounds[k], bounds[k]) : Math.max(regionBounds[k], bounds[k]);
        }
        function contains(x, y) {
            if (!Number.isFinite(x) || !Number.isFinite(y) || !overlaps(root.bounds, [x, y, x, y]))
                return false;
            let inside = false, boundary = false;
            visit(root, [x, y, Infinity, y], e => {
                const [px, py] = e.p, qy = e.q[1], dx = e.dx, dy = e.dy;
                const cross = (x - px) * dy - (y - py) * dx;
                const tolerance = 8 * EPS * (Math.abs((x - px) * dy) + Math.abs((y - py) * dx));
                if (x >= e.bounds[0] && x <= e.bounds[2] && Math.abs(cross) <= tolerance)
                    boundary = true;
                if ((py > y) !== (qy > y) && x < px + (y - py) * dx / dy)
                    inside = !inside;
            });
            return boundary || inside;
        }
        function clipEllipse(c, u, v, candidates, cuts = [0, 1], accept) {
            if (!valid(c) || !valid(u) || !valid(v))
                return null;
            const scale = Math.max(Math.abs(u[0]), Math.abs(u[1]), Math.abs(v[0]), Math.abs(v[1]));
            if (!(scale > 0) || scale > 1e150 || scale < 1e-150)
                return null;
            const ux = u[0] / scale, uy = u[1] / scale, vx = v[0] / scale, vy = v[1] / scale;
            const det = ux * vy - uy * vx;
            if (Math.abs(det) < 1e-12)
                return null;
            const rx = Math.hypot(u[0], v[0]), ry = Math.hypot(u[1], v[1]);
            const extent = Math.max(root.bounds[2] - root.bounds[0], root.bounds[3] - root.bounds[1]);
            if (edges.length && (scale > Math.max(extent, 1e-150) * 1e10 || Math.max(Math.abs(c[0]), Math.abs(c[1])) * EPS > scale * 1e-6))
                return null;
            const eb = [c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry];
            if (!edges.length || !overlaps(root.bounds, eb))
                return [];
            let unsafe = false;
            function intersect(e) {
                const x = (e.p[0] - c[0]) / scale, y = (e.p[1] - c[1]) / scale;
                const px = (vy * x - vx * y) / det, py = (ux * y - uy * x) / det;
                const qx = (e.q[0] - c[0]) / scale, qy = (e.q[1] - c[1]) / scale;
                const qpx = (vy * qx - vx * qy) / det, qpy = (ux * qy - uy * qx) / det;
                const dx = qpx - px, dy = qpy - py, length = Math.hypot(dx, dy);
                if (!Number.isFinite(px) || !Number.isFinite(py) || !Number.isFinite(qpx) || !Number.isFinite(qpy) || !(length > 0)) {
                    unsafe = true;
                    return;
                }
                const norm = Math.hypot(px, py);
                if (Math.max(norm, Math.hypot(qpx, qpy)) > 1e8) {
                    unsafe = true;
                    return;
                }
                const ex = dx / length, ey = dy / length;
                // Unit-speed segment in the inverse ellipse frame meets the unit circle.
                // D = 1 - cross(p,e)^2 avoids cancellation of b*b - a*c.
                const b = px * ex + py * ey, h = px * ey - py * ex;
                let d = (1 - Math.abs(h)) * (1 + Math.abs(h));
                if (d < -32 * EPS * Math.max(1, h * h))
                    return;
                d = Math.max(0, d);
                const r = Math.sqrt(d), stable = -b - (b < 0 ? -r : r);
                const roots = stable === 0 ? [-b] : [stable, (norm - 1) * (norm + 1) / stable];
                for (const s of roots) {
                    const t = s / length;
                    if (t < -32 * EPS || t > 1 + 32 * EPS)
                        continue;
                    const f = Math.max(0, Math.min(1, t));
                    let angle = Math.atan2(py + f * dy, px + f * dx) / TAU;
                    if (angle < 0)
                        angle += 1;
                    cuts.push(angle);
                }
            }
            if (candidates) {
                for (const edge of candidates)
                    if (overlaps(edge.bounds, eb))
                        intersect(edge);
            }
            else
                visit(root, eb, intersect);
            if (unsafe)
                return null;
            return intervals(cuts, t => {
                const a = TAU * t, co = Math.cos(a), si = Math.sin(a);
                return [c[0] + u[0] * co + v[0] * si, c[1] + u[1] * co + v[1] * si];
            }, contains, accept);
        }
        return {
            bounds: Object.freeze(regionBounds), contains,
            clipEllipse,
            sphereFamily(c, r, axis, e, f) {
                const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
                const basis = [axis, e, f];
                if (!valid(c) || !(r > 0) || !Number.isFinite(r) || r < 1e-150 || r > 1e150 ||
                    basis.some(a => a.length < 3 || !a.slice(0, 3).every(Number.isFinite) || Math.abs(dot(a, a) - 1) > 1e-9) ||
                    Math.abs(dot(axis, e)) > 1e-9 || Math.abs(dot(axis, f)) > 1e-9 || Math.abs(dot(e, f)) > 1e-9 ||
                    Math.abs(e[0] * f[1] - e[1] * f[0]) < 1e-12)
                    return () => null;
                // Retain an immutable family chart even if the caller reuses its vectors.
                const center = c.slice(0, 2), a = axis.slice(0, 3), u = e.slice(0, 3), v = f.slice(0, 3);
                const count = Math.max(32, Math.min(1024, Math.ceil(Math.sqrt(edges.length) * 8)));
                const bins = Array.from({ length: count }, () => []);
                const bin = (h) => Math.max(0, Math.min(count - 1, Math.floor((h + 1) * .5 * count)));
                let refs = 0;
                for (const edge of edges) {
                    const px = (edge.p[0] - center[0]) / r, py = (edge.p[1] - center[1]) / r;
                    const qx = (edge.q[0] - center[0]) / r, qy = (edge.q[1] - center[1]) / r;
                    const dx = qx - px, dy = qy - py, length2 = dx * dx + dy * dy;
                    if (![px, py, qx, qy, length2].every(Number.isFinite))
                        return () => null;
                    const t = length2 > 0 ? Math.max(0, Math.min(1, -(px * dx + py * dy) / length2)) : 0;
                    const near2 = (px + t * dx) ** 2 + (py + t * dy) ** 2;
                    const far2 = Math.max(px * px + py * py, qx * qx + qy * qy);
                    // Outward error covers rounded silhouette vertices, including segments
                    // with endpoints just outside the sphere but interior points inside it.
                    const error = 64 * EPS * Math.max(1, far2);
                    if (near2 > 1 + error)
                        continue;
                    const zlo = Math.sqrt(Math.max(0, 1 - far2 - error));
                    const zhi = Math.sqrt(Math.max(0, 1 - near2 + error));
                    const hp = a[0] * px + a[1] * py, hq = a[0] * qx + a[1] * qy;
                    const padding = 1e-8 + 128 * EPS * Math.max(1, Math.abs(hp), Math.abs(hq));
                    const low = Math.min(hp, hq) + Math.min(a[2] * zlo, a[2] * zhi) - padding;
                    const high = Math.max(hp, hq) + Math.max(a[2] * zlo, a[2] * zhi) + padding;
                    if (high < -1 || low > 1)
                        continue;
                    const first = bin(low), last = bin(high);
                    refs += last - first + 1;
                    // Bound chart memory; parent can use its generic fallback for pathological
                    // long crossing edges instead of retaining millions of duplicate refs.
                    if (refs > 2000000)
                        return () => null;
                    for (let i = first; i <= last; i++)
                        bins[i].push(edge);
                }
                return h => {
                    if (!Number.isFinite(h) || Math.abs(h) > 1)
                        return null;
                    const radial = Math.sqrt(Math.max(0, (1 - h) * (1 + h))), radius = r * radial;
                    if (!(radius > 0))
                        return null;
                    const c = [center[0] + r * h * a[0], center[1] + r * h * a[1]];
                    const eu = [radius * u[0], radius * u[1]], ev = [radius * v[0], radius * v[1]];
                    const z0 = h * a[2], zc = radial * u[2], zs = radial * v[2], amplitude = Math.hypot(zc, zs);
                    const cuts = [0, 1];
                    if (amplitude > 0 && Math.abs(z0) <= amplitude) {
                        const phase = Math.atan2(zs, zc), alpha = Math.acos(Math.max(-1, Math.min(1, -z0 / amplitude)));
                        for (const angle of [phase - alpha, phase + alpha]) {
                            const t = angle / TAU;
                            cuts.push(t - Math.floor(t));
                        }
                    }
                    // The height index contains only front-lift intersections. Explicit
                    // silhouette cuts prevent an uncut back arc from becoming visible.
                    return clipEllipse(c, eu, ev, bins[bin(h)], cuts, t => z0 + zc * Math.cos(TAU * t) + zs * Math.sin(TAU * t) >= 0);
                };
            },
            clipLine(a, b) {
                if (!valid(a) || !valid(b))
                    return [];
                const dx = b[0] - a[0], dy = b[1] - a[1];
                if (dx === 0 && dy === 0)
                    return contains(a[0], a[1]) ? [[0, 1]] : [];
                const cuts = [0, 1], lb = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
                if (!overlaps(root.bounds, lb))
                    return [];
                visit(root, lb, e => {
                    const ex = e.dx, ey = e.dy, px = e.p[0] - a[0], py = e.p[1] - a[1];
                    const det = dx * ey - dy * ex;
                    if (det !== 0) {
                        const t = (px * ey - py * ex) / det, s = (px * dy - py * dx) / det;
                        if (t >= 0 && t <= 1 && s >= 0 && s <= 1)
                            cuts.push(t);
                    }
                    else if (px * dy - py * dx === 0) {
                        // Both overlap endpoints are cuts; midpoint classification handles
                        // coincident segments without parity toggles or invented bridges.
                        const axis = Math.abs(dx) >= Math.abs(dy) ? 0 : 1, delta = axis === 0 ? dx : dy;
                        cuts.push(Math.max(0, Math.min(1, (e.p[axis] - a[axis]) / delta)), Math.max(0, Math.min(1, (e.q[axis] - a[axis]) / delta)));
                    }
                });
                return intervals(cuts, t => [a[0] + dx * t, a[1] + dy * t], contains);
            }
        };
    }

    var TOL = .0015, SNAP = .00003, ROUND = .002;
    var MAX_EDGES = 250000, MAX_REFS = 2000000;
    function finite(x) { return typeof x === 'number' && Number.isFinite(x); }
    function point(p) { return p && finite(p[0]) && finite(p[1]); }
    function box() { return [Infinity, Infinity, -Infinity, -Infinity]; }
    function include(b, p) {
        b[0] = Math.min(b[0], p[0]);
        b[1] = Math.min(b[1], p[1]);
        b[2] = Math.max(b[2], p[0]);
        b[3] = Math.max(b[3], p[1]);
    }
    function insideBox(b, x, y) { return x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3]; }
    function distance2(e, x, y) {
        var dx = e.dx, dy = e.dy;
        var t = Math.max(0, Math.min(1, ((x - e.p[0]) * dx + (y - e.p[1]) * dy) / e.length2));
        var a = x - e.p[0] - t * dx, b = y - e.p[1] - t * dy;
        return a * a + b * b;
    }
    // Bounded rectangular grid. A long edge is registered in every cell touched
    // by its box (not just its endpoints), making radius searches conservative.
    function grid(bounds, count) {
        var n = Math.max(1, Math.min(128, Math.ceil(Math.sqrt(count / 4))));
        var w = bounds[2] - bounds[0], h = bounds[3] - bounds[1];
        var nx = Math.max(1, Math.min(128, Math.ceil(n * Math.sqrt(w / h))));
        var ny = Math.max(1, Math.min(128, Math.ceil(n * Math.sqrt(h / w))));
        var cells = new Array(nx * ny), refs = 0;
        function ix(x) { return Math.max(0, Math.min(nx - 1, Math.floor((x - bounds[0]) / w * nx))); }
        function iy(y) { return Math.max(0, Math.min(ny - 1, Math.floor((y - bounds[1]) / h * ny))); }
        return {
            ix: ix, iy: iy, nx: nx, cells: cells,
            add: function (b, id) {
                var x0 = ix(b[0]), x1 = ix(b[2]), y0 = iy(b[1]), y1 = iy(b[3]);
                refs += (x1 - x0 + 1) * (y1 - y0 + 1);
                if (refs > MAX_REFS)
                    return false;
                for (var y = y0; y <= y1; y++)
                    for (var x = x0; x <= x1; x++) {
                        var k = y * nx + x;
                        if (!cells[k])
                            cells[k] = [];
                        cells[k].push(id);
                    }
                return true;
            }
        };
    }
    function create(scene, segments, nodes, project, scale) {
        // project/scale belong to the shared builder's API; geometry is already SVG.
        if (!Array.isArray(scene) || !Array.isArray(segments) || !nodes || !(scale > 0) || !finite(scale))
            return null;
        try {
            return build(scene, segments, nodes);
        }
        catch (_) {
            return null;
        }
    }
    function build(scene, segments, nodes) {
        if (scene.length > 10000 || segments.length > MAX_EDGES)
            return null;
        var owners = scene.map(function (_, id) { return { id: id, starts: new Map(), ins: new Map(), directed: [], edges: [], bounds: box() }; });
        var edges = [], bounds = box(), error = TOL + SNAP + ROUND;
        function label(id) { return Number.isInteger(id) && id >= -1 && id < scene.length; }
        function attach(id, start, end, poly, reverse) {
            if (id === -1)
                return true;
            var o = owners[id];
            if (o.starts.has(start) || o.ins.has(end))
                return false;
            var e = { start: start, end: end, poly: poly, reverse: reverse, used: false };
            o.starts.set(start, e);
            o.ins.set(end, e);
            o.directed.push(e);
            return true;
        }
        for (var si = 0; si < segments.length; si++) {
            var s = segments[si];
            if (!s || !label(s.left) || !label(s.right))
                return null;
            if (s.left === s.right)
                continue; // includes invisible cuts, not colour equality
            var c = s.c, p = nodes[s.start], q = nodes[s.end];
            if (!c || typeof c.at !== 'function' || !point(p) || !point(q) || !finite(s.a) || !finite(s.b) || s.a === s.b)
                return null;
            var pa = c.at(s.a), pb = c.at(s.b);
            if (!point(pa) || !point(pb) || Math.hypot(p[0] - pa[0], p[1] - pa[1]) > SNAP || Math.hypot(q[0] - pb[0], q[1] - pb[1]) > SNAP)
                return null;
            var steps = 1;
            if (!c.line) {
                if (!point(c.U) || !point(c.V) || !point(c.C) || !(c.radius > 0) || !finite(c.radius))
                    return null;
                // Largest singular value of [U V] also covers nonorthogonal ellipse
                // bases; never blindly trust a radius smaller than this analytic bound.
                var uu = c.U[0] * c.U[0] + c.U[1] * c.U[1], vv = c.V[0] * c.V[0] + c.V[1] * c.V[1];
                var uv = c.U[0] * c.V[0] + c.U[1] * c.V[1];
                var radius = Math.max(c.radius, Math.sqrt((uu + vv + Math.hypot(uu - vv, 2 * uv)) / 2));
                if (!finite(radius))
                    return null;
                steps = Math.max(1, Math.ceil(Math.abs(s.b - s.a) / Math.min(Math.PI / 4, Math.sqrt(8 * TOL / radius))));
            }
            if (!finite(steps) || edges.length + steps > MAX_EDGES)
                return null;
            var poly = [], prev = [p[0], p[1]];
            for (var j = 1; j <= steps; j++) {
                var next = j === steps ? [q[0], q[1]] : c.at(s.a + (s.b - s.a) * j / steps);
                if (!point(next))
                    return null;
                next = [next[0], next[1]];
                if (next[0] === prev[0] && next[1] === prev[1])
                    return null;
                var eb = [Math.min(prev[0], next[0]), Math.min(prev[1], next[1]), Math.max(prev[0], next[0]), Math.max(prev[1], next[1])];
                var dx = next[0] - prev[0], dy = next[1] - prev[1];
                var edge = { p: prev, q: next, dx: dx, dy: dy, length2: dx * dx + dy * dy, bounds: eb };
                poly.push(edge);
                edges.push(edge);
                include(bounds, prev);
                include(bounds, next);
                prev = next;
            }
            if (!attach(s.left, s.start, s.end, poly, false) || !attach(s.right, s.end, s.start, poly, true))
                return null;
        }
        var active = [], totalRowRefs = 0;
        // Retain exactly the validated owner polygons; build each clipping BVH lazily.
        var surfaceEdges = new Map(), surfaces = new Map();
        function surface(id) {
            var polygon = surfaceEdges.get(id);
            if (!polygon)
                return null;
            var region = surfaces.get(id);
            if (!region) {
                region = createRegion(polygon, owners[id].bounds);
                surfaces.set(id, region);
            }
            return region;
        }
        for (var oi = 0; oi < owners.length; oi++) {
            var o = owners[oi];
            if (!o.directed.length)
                continue; // valid fully occluded source, even white
            if (o.starts.size !== o.ins.size)
                return null;
            for (var v of o.starts.keys())
                if (!o.ins.has(v))
                    return null;
            // Explicitly walk each oriented component. Never repair a missing link.
            for (var first of o.directed) {
                if (first.used)
                    continue;
                var current = first, count = 0;
                do {
                    if (!current || current.used || ++count > o.directed.length)
                        return null;
                    current.used = true;
                    for (var pe of current.poly) {
                        o.edges.push(pe);
                        include(o.bounds, pe.p);
                        include(o.bounds, pe.q);
                    }
                    current = o.starts.get(current.end);
                } while (current !== first);
            }
            if (!(o.bounds[2] > o.bounds[0]) || !(o.bounds[3] > o.bounds[1]))
                return null;
            var rows = Math.max(1, Math.min(256, Math.ceil(Math.sqrt(o.edges.length))));
            o.rows = new Array(rows);
            o.rowScale = rows / (o.bounds[3] - o.bounds[1]);
            for (var e of o.edges) {
                var lo = Math.max(0, Math.min(rows - 1, Math.floor((e.bounds[1] - o.bounds[1]) * o.rowScale)));
                var hi = Math.max(0, Math.min(rows - 1, Math.floor((e.bounds[3] - o.bounds[1]) * o.rowScale)));
                totalRowRefs += hi - lo + 1;
                if (totalRowRefs > MAX_REFS)
                    return null;
                for (var ri = lo; ri <= hi; ri++) {
                    if (!o.rows[ri])
                        o.rows[ri] = [];
                    o.rows[ri].push(e);
                }
            }
            // Dot queries keep their unchanged row index. Clipping retains the same
            // polygon edges, including every disconnected component and hole.
            surfaceEdges.set(o.id, o.edges);
            // The build-only graph fields are discarded after indexing.
            delete o.starts;
            delete o.ins;
            delete o.directed;
            delete o.edges;
            active.push(o);
        }
        if (!active.length)
            return { query: function () { return null; }, surface: surface };
        if (!(bounds[2] > bounds[0]) || !(bounds[3] > bounds[1]))
            return null;
        error += 128 * Number.EPSILON * Math.max(1, Math.abs(bounds[0]), Math.abs(bounds[1]), Math.abs(bounds[2]), Math.abs(bounds[3]));
        var ownerGrid = grid(bounds, active.length * 16), edgeGrid = grid(bounds, edges.length);
        for (var ai = 0; ai < active.length; ai++)
            if (!ownerGrid.add(active[ai].bounds, ai))
                return null;
        for (var ei = 0; ei < edges.length; ei++)
            if (!edgeGrid.add(edges[ei].bounds, ei))
                return null;
        var seen = new Uint32Array(edges.length), stamp = 0;
        function contains(o, x, y) {
            if (!insideBox(o.bounds, x, y))
                return false;
            var row = Math.max(0, Math.min(o.rows.length - 1, Math.floor((y - o.bounds[1]) * o.rowScale)));
            var list = o.rows[row] || [], yes = false;
            for (var i = 0; i < list.length; i++) {
                var p = list[i].p, q = list[i].q;
                if ((p[1] > y) !== (q[1] > y) && x < p[0] + (y - p[1]) * list[i].dx / list[i].dy)
                    yes = !yes;
            }
            return yes;
        }
        return { surface: surface, query: function (x, y, maxRadius) {
                if (!finite(x) || !finite(y) || !finite(maxRadius) || !(maxRadius > 0) || !insideBox(bounds, x, y))
                    return null;
                var candidates = ownerGrid.cells[ownerGrid.iy(y) * ownerGrid.nx + ownerGrid.ix(x)] || [], owner = -1;
                for (var i = 0; i < candidates.length; i++) {
                    var o = active[candidates[i]];
                    if (contains(o, x, y)) {
                        if (owner !== -1)
                            return null;
                        owner = o.id;
                    }
                }
                if (owner === -1)
                    return null;
                // Other owners' edges count too: slightly conservative near disconnected
                // islands but avoids any local ownership assumption in the distance test.
                var radius = maxRadius + error, best = radius * radius;
                if (!finite(best))
                    return null;
                var x0 = edgeGrid.ix(x - radius), x1 = edgeGrid.ix(x + radius);
                var y0 = edgeGrid.iy(y - radius), y1 = edgeGrid.iy(y + radius);
                stamp = (stamp + 1) >>> 0;
                if (stamp === 0) {
                    seen.fill(0);
                    stamp = 1;
                }
                for (var iy = y0; iy <= y1; iy++)
                    for (var ix = x0; ix <= x1; ix++) {
                        var list = edgeGrid.cells[iy * edgeGrid.nx + ix];
                        if (!list)
                            continue;
                        for (var k = 0; k < list.length; k++) {
                            var id = list[k];
                            if (seen[id] === stamp)
                                continue;
                            seen[id] = stamp;
                            var e = edges[id], b = e.bounds;
                            var dx = Math.max(b[0] - x, 0, x - b[2]), dy = Math.max(b[1] - y, 0, y - b[3]);
                            if (dx * dx + dy * dy >= best)
                                continue;
                            best = Math.min(best, distance2(e, x, y));
                            if (best <= error * error)
                                return null;
                        }
                    }
                var clearance = Math.min(maxRadius, Math.sqrt(best) - error);
                return clearance > 0 ? { id: owner, clearance: clearance } : null;
            } };
    }

    exports.create = create;

    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });

    return exports;

})({});
if (typeof module !== 'undefined' && module.exports) module.exports = MolDotRegions;
