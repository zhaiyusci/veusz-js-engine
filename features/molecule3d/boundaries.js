/* Generated from src/boundaries.ts by npm run build. Edit TypeScript, not this file. */
var MolBoundaries = (function (exports) {
    'use strict';

    const root = globalThis;
    function getDotRegions() {
        return typeof module !== 'undefined' && module.exports ? require('./dot-regions.js') : root.MolDotRegions;
    }

    const TAU = 2 * Math.PI, dot = (a, b) => a.reduce((v, x, i) => v + x * b[i], 0);
    const add = (a, b) => a.map((x, i) => x + b[i]), mul = (a, k) => a.map(x => x * k), sub = (a, b) => add(a, mul(b, -1));
    const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const norm = (a) => mul(a, 1 / Math.hypot(...a)), dist = (a, b) => Math.hypot(...sub(a, b));
    const cross2 = (a, b) => a[0] * b[1] - a[1] * b[0], fmt = (p) => p.map(x => Number(x.toFixed(4))).join(' ');
    // Isolate real polynomial roots on a bounded interval using derivative roots.
    // Unlike sign-change sampling this also finds double roots (tangent arcs).
    function roots(p, lo, hi) {
        const size = Math.max(...p.map(Math.abs));
        if (!size)
            return null; // coincident curves: caller falls back rather than guessing
        p = p.map(x => x / size);
        while (p.length > 1 && Math.abs(p.at(-1)) < 1e-13)
            p.pop();
        const value = (x) => p.reduceRight((v, c) => v * x + c, 0);
        if (p.length === 1)
            return [];
        if (p.length === 2) {
            const t = -p[0] / p[1];
            return t >= lo - 1e-10 && t <= hi + 1e-10 ? [Math.max(lo, Math.min(hi, t))] : [];
        }
        const critical = roots(p.slice(1).map((x, i) => x * (i + 1)), lo, hi) || [];
        const cuts = [lo, ...critical, hi], out = [];
        for (const x of cuts)
            if (Math.abs(value(x)) < 1e-10)
                out.push(x);
        for (let i = 1; i < cuts.length; i++) {
            let a = cuts[i - 1], b = cuts[i], fa = value(a), fb = value(b);
            if (fa * fb >= 0 || Math.abs(fa) < 1e-10 || Math.abs(fb) < 1e-10)
                continue;
            for (let j = 0; j < 48; j++) {
                const m = (a + b) / 2, f = value(m);
                if (f * fa > 0) {
                    a = m;
                    fa = f;
                }
                else
                    b = m;
            }
            out.push((a + b) / 2);
        }
        return out;
    }
    const local = (c, p) => { const d = sub(p, c.C); return [cross2(d, c.V) / c.det, cross2(c.U, d) / c.det]; };
    const parameter = (c, p) => c.line ? dot(sub(p, c.A), c.D) / dot(c.D, c.D) : ((Math.atan2(...local(c, p).reverse()) % TAU) + TAU) % TAU;
    // Equality of supports, independent of parameter orientation/phase. Keep this
    // near roundoff: proximity alone is not a license to erase a narrow region.
    function sameCarrier(a, b) {
        if (!!a.line !== !!b.line)
            return false;
        if (a.line) {
            const la = Math.hypot(...a.D), lb = Math.hypot(...b.D);
            return Math.abs(cross2(a.D, b.D)) <= 1e-12 * la * lb &&
                Math.abs(cross2(sub(b.A, a.A), a.D)) <= 1e-8 * la;
        }
        // Most ellipse pairs have different centers: reject without temporary
        // vectors before the exact near-coincidence check below.
        if (Math.abs(a.C[0] - b.C[0]) > 1e-8 || Math.abs(a.C[1] - b.C[1]) > 1e-8 || dist(a.C, b.C) > 1e-8)
            return false;
        const U = [cross2(a.U, b.V) / b.det, cross2(b.U, a.U) / b.det];
        const V = [cross2(a.V, b.V) / b.det, cross2(b.U, a.V) / b.det];
        return Math.max(Math.abs(dot(U, U) - 1), Math.abs(dot(V, V) - 1), Math.abs(dot(U, V))) < 1e-11;
    }
    // Shared projected-curve solver: both the face arrangement and hatch clipping
    // use these intersections. emit receives parameters on a and b respectively.
    function intersections(a, b, emit) {
        if (a.box[0] > b.box[2] + 1e-6 || b.box[0] > a.box[2] + 1e-6 || a.box[1] > b.box[3] + 1e-6 || b.box[1] > a.box[3] + 1e-6)
            return;
        function hit(t) {
            const p = a.at(t), q = parameter(b, p);
            if (q < -1e-8 || q > b.end + 1e-8 || dist(p, b.at(q)) > .00002)
                return;
            emit(t, Math.max(0, Math.min(b.end, q)));
        }
        if (a.line && b.line) {
            const d = cross2(a.D, b.D);
            if (Math.abs(d) < 1e-10) {
                if (sameCarrier(a, b)) {
                    // A collinear finite overlap has endpoint events, not isolated roots.
                    for (const t of [0, 1])
                        hit(t);
                    for (const q of [0, 1]) {
                        const t = parameter(a, b.at(q));
                        if (t >= 0 && t <= 1)
                            hit(t);
                    }
                }
            }
            else {
                const t = cross2(sub(b.A, a.A), b.D) / d;
                if (t >= 0 && t <= 1)
                    hit(t);
            }
        }
        else if (a.line || b.line) {
            if (!a.line) {
                intersections(b, a, (q, t) => emit(t, q));
                return;
            }
            const P = local(b, a.A), Q = sub(local(b, add(a.A, a.D)), P);
            for (const t of roots([dot(P, P) - 1, 2 * dot(P, Q), dot(Q, Q)], 0, 1) || [])
                hit(t);
        }
        else {
            const C = local(b, a.C), U = sub(local(b, add(a.C, a.U)), C), V = sub(local(b, add(a.C, a.V)), C);
            // tan(theta/2) on four bounded charts avoids roots at infinity.
            for (let quadrant = 0; quadrant < 4; quadrant++) {
                const angle = quadrant * Math.PI / 2, cos = Math.cos(angle), sin = Math.sin(angle);
                const u = add(mul(U, cos), mul(V, sin)), v = add(mul(U, -sin), mul(V, cos));
                const p = add(C, u), q = mul(v, 2), r = sub(C, u);
                const poly = [dot(p, p) - 1, 2 * dot(p, q), dot(q, q) + 2 * dot(p, r) - 2, 2 * dot(q, r), dot(r, r) - 1];
                const rr = roots(poly, -Math.tan(Math.PI / 8), Math.tan(Math.PI / 8));
                if (rr === null || Math.max(...poly.map(Math.abs)) < 1e-10)
                    throw new Error('coincident ellipses');
                for (const t of rr)
                    hit((angle + 2 * Math.atan(t) + TAU) % TAU);
            }
        }
    }
    function build(scene, depthAt, project, scale) {
        const spheres = scene.filter((s) => s.kind === 'sphere'), cylinders = scene.filter((s) => s.kind === 'cylinder');
        if (!spheres.length || scene.length > 200 || !(scale > 0))
            return null;
        // This fast path proves its geometry assumptions before omitting any curves.
        // Partial sphere intersections contribute their true 3-D seam circles.
        // Degenerate/nested balls, free caps and incidental exposed sphere/rod
        // contacts still use the general path, never a center-sorted drawing.
        if (scene.some(s => !(s.r > 0) || s.r * scale > 10000 || s.r * scale < .01 ||
            (s.kind === 'sphere' ? s.c : s.a).some(x => !Number.isFinite(x) || Math.abs(x) > 1e4)))
            return null;
        const sphereSeams = [];
        for (let i = 0; i < spheres.length; i++)
            for (let j = 0; j < i; j++) {
                const a = spheres[i], b = spheres[j], d = dist(a.c, b.c), sum = a.r + b.r;
                if (d > sum + 1e-8)
                    continue;
                // Keep uncertain tangencies and nested/coincident surfaces conservative.
                if (d >= sum - 1e-8 || d <= Math.abs(a.r - b.r) + 1e-8)
                    return null;
                const axis = mul(sub(b.c, a.c), 1 / d), h = (a.r * a.r - b.r * b.r + d * d) / (2 * d);
                const radius = Math.sqrt(a.r * a.r - h * h);
                if (!(radius > 1e-8))
                    return null;
                const e = norm(cross(axis, Math.abs(axis[2]) < .95 ? [0, 0, 1] : [0, 1, 0])), f = cross(axis, e);
                sphereSeams.push({ center: add(a.c, mul(axis, h)), u: mul(e, radius), v: mul(f, radius) });
            }
        const ends = [], covered = new Set();
        for (const c of cylinders) {
            if (Math.abs(dot(c.u, c.u) - 1) > 1e-10 || !(c.length > 0))
                return null;
            const b = add(c.a, mul(c.u, c.length));
            const aSphere = spheres.find(s => dist(s.c, c.a) < 1e-10), bSphere = spheres.find(s => dist(s.c, b) < 1e-10);
            if (!aSphere || !bSphere || aSphere === bSphere || c.r >= Math.min(aSphere.r, bSphere.r))
                return null;
            // Legacy ray tolerances become ill-conditioned close to camera-parallel.
            // This guard also precedes covered-carrier omission: mathematical solid
            // containment does not bound the legacy solver's expanded near-axis hits.
            const axial = 1 - c.u[2] * c.u[2];
            if (axial > 1e-12 && axial < 1e-7)
                return null;
            ends.push([aSphere, bSphere]);
            // Every cross-sectional disk is contained in at least one endpoint ball.
            // A strict margin covers endpoint matching/roundoff; retain physical rods
            // in scene (and all raw owner IDs), omit only their invisible carriers.
            if (Math.sqrt(aSphere.r * aSphere.r - c.r * c.r) + Math.sqrt(bSphere.r * bSphere.r - c.r * c.r) > c.length + 1e-8) {
                covered.add(c);
                continue;
            }
            for (const s of spheres) {
                if (s === aSphere || s === bSphere)
                    continue;
                const t = Math.max(0, Math.min(c.length, dot(sub(s.c, c.a), c.u)));
                if (dist(s.c, add(c.a, mul(c.u, t))) <= s.r + c.r + 1e-8)
                    return null;
            }
        }
        const origin = project([0, 0, 0]), curves = [];
        const vector = (v) => [v[0] * scale, -v[1] * scale];
        function circle(c, u, v, source = null) {
            const C = project(c), U = vector(u), V = vector(v), radius = Math.max(Math.hypot(...u), Math.hypot(...v)) * scale;
            const det = cross2(U, V);
            if (Math.abs(det) < 1e-10) {
                const axis = norm(Math.hypot(...U) > Math.hypot(...V) ? U : V), half = Math.hypot(dot(U, axis), dot(V, axis));
                line2(sub(C, mul(axis, half)), add(C, mul(axis, half)));
                return;
            }
            if (Math.abs(det) / radius < .0001)
                throw new Error('ill-conditioned ellipse');
            curves.push({ C, U, V, det, source, world: t => add(c, add(mul(u, Math.cos(t)), mul(v, Math.sin(t)))),
                at: t => add(C, add(mul(U, Math.cos(t)), mul(V, Math.sin(t)))),
                tangent: t => add(mul(U, -Math.sin(t)), mul(V, Math.cos(t))),
                cuts: [0, Math.PI / 2, Math.PI, Math.PI * 1.5, TAU], end: TAU, radius,
                box: [C[0] - Math.hypot(U[0], V[0]), C[1] - Math.hypot(U[1], V[1]), C[0] + Math.hypot(U[0], V[0]), C[1] + Math.hypot(U[1], V[1])] });
        }
        function line2(A, B) {
            const D = sub(B, A);
            if (Math.hypot(...D) < 1e-8)
                return;
            curves.push({ line: true, A, D, at: t => add(A, mul(D, t)), tangent: () => D, cuts: [0, 1], end: 1,
                box: [Math.min(A[0], B[0]), Math.min(A[1], B[1]), Math.max(A[0], B[0]), Math.max(A[1], B[1])] });
        }
        try {
            for (const s of spheres)
                circle(s.c, [s.r, 0, 0], [0, s.r, 0], s);
            // No sphere/cylinder Contact metadata: these seams use the general
            // projected intersection solver when clipping surface hatch circles.
            for (const seam of sphereSeams)
                circle(seam.center, seam.u, seam.v);
            cylinders.forEach((c, i) => {
                if (covered.has(c))
                    return;
                const u = c.u, e = norm(cross(u, Math.abs(u[2]) < .95 ? [0, 0, 1] : [0, 1, 0])), f = cross(u, e);
                for (let end = 0; end < 2; end++) {
                    const s = ends[i][end], h = Math.sqrt(s.r * s.r - c.r * c.r);
                    const before = curves.length, offset = end ? -h : h;
                    circle(add(s.c, mul(u, offset)), mul(e, c.r), mul(f, c.r));
                    if (curves.length > before)
                        curves.at(-1).contact = { sphere: s, cylinder: c, axis: u, offset };
                }
                if (Math.hypot(u[0], u[1]) > 1e-10) {
                    const edge = mul(norm([-u[1], u[0], 0]), c.r);
                    for (const sign of [-1, 1]) {
                        const a = add(c.a, mul(edge, sign));
                        line2(project(a), project(add(a, mul(u, c.length))));
                    }
                }
            });
            // Arrange unique geometric supports. Raw curves retain their physical
            // ownership: coincident projection does NOT imply coincident 3-D contact.
            const raw = curves.splice(0), groups = [];
            for (const c of raw) {
                let group = groups.find(g => sameCarrier(c, g[0]));
                if (group)
                    group.push(c);
                else
                    groups.push([c]);
            }
            for (const members of groups) {
                const first = members[0];
                if (!first.line) {
                    first.members = members;
                    for (const c of members.slice(1))
                        for (const t of c.cuts)
                            first.cuts.push(parameter(first, c.at(t)));
                    curves.push(first);
                }
                else {
                    // Union finite collinear generators, but never bridge a gap. Every
                    // original endpoint remains an event, including endpoints in overlaps.
                    const ranges = members.map(c => {
                        const ts = [parameter(first, c.A), parameter(first, c.at(1))].sort((a, b) => a - b);
                        return { lo: ts[0], hi: ts[1], c };
                    }).sort((a, b) => a.lo - b.lo);
                    for (let i = 0; i < ranges.length;) {
                        const lo = ranges[i].lo, part = [ranges[i++]];
                        let hi = part[0].hi;
                        while (i < ranges.length && ranges[i].lo <= hi) {
                            hi = Math.max(hi, ranges[i].hi);
                            part.push(ranges[i++]);
                        }
                        line2(first.at(lo), first.at(hi));
                        const carrier = curves.at(-1);
                        carrier.members = part.map(r => r.c);
                        for (const r of part)
                            for (const t of [r.lo, r.hi])
                                carrier.cuts.push((t - lo) / (hi - lo));
                    }
                }
            }
            for (const c of curves)
                c.contacts = c.members.filter(m => m.contact).map(m => m.contact);
            // Intersections are solved on the analytic projected curves, not pixels.
            for (let i = 0; i < curves.length; i++)
                for (let j = 0; j < i; j++) {
                    const a = curves[i], b = curves[j];
                    intersections(a, b, (t, q) => { a.cuts.push(t); b.cuts.push(q); });
                }
        }
        catch (_) {
            return null;
        }
        function owner(p) {
            const x = (p[0] - origin[0]) / scale, y = (origin[1] - p[1]) / scale;
            let z = -Infinity, best = -1;
            for (let i = 0; i < scene.length; i++) {
                const shape = scene[i];
                // Topological side tests need the mathematical silhouette, not the
                // depth oracle's slightly expanded tangent-hit tolerance. Otherwise
                // an infinitesimal outside probe can be classified inside BOTH sides.
                if (shape.kind === 'sphere') {
                    if ((x - shape.c[0]) ** 2 + (y - shape.c[1]) ** 2 > shape.r * shape.r)
                        continue;
                }
                else {
                    const axis2 = shape.u[0] ** 2 + shape.u[1] ** 2;
                    const perpendicular = (x - shape.a[0]) * shape.u[1] - (y - shape.a[1]) * shape.u[0];
                    if (axis2 > 1e-12 && perpendicular * perpendicular > shape.r * shape.r * axis2)
                        continue;
                }
                const d = depthAt(shape, x, y);
                if (Number.isFinite(d) && (d > z || (d === z && shape.kind === 'cylinder'))) {
                    z = d;
                    best = i;
                }
            }
            return best;
        }
        // Canonical shared vertices; intersections can arrive via several curves.
        const nodes = [], buckets = new Map(), snap = .00002;
        function node(p) {
            const x = Math.round(p[0] / snap), y = Math.round(p[1] / snap);
            for (let dx = -1; dx <= 1; dx++)
                for (let dy = -1; dy <= 1; dy++) {
                    const candidates = buckets.get((x + dx) + ',' + (y + dy)) || [];
                    for (const id of candidates)
                        if (dist(nodes[id], p) < snap)
                            return id;
                }
            const id = nodes.length;
            nodes.push(p);
            const key = x + ',' + y;
            if (!buckets.has(key))
                buckets.set(key, []);
            buckets.get(key).push(id);
            return id;
        }
        const segments = [], outlines = new Map();
        for (const c of curves) {
            c.cuts.sort((a, b) => a - b);
            c.cuts = c.cuts.filter((t, i, a) => !i || t - a[i - 1] > 1e-9);
            const silhouettes = c.members.filter(m => m.source);
            for (const raw of silhouettes)
                outlines.set(raw.source, []);
            for (let i = 1; i < c.cuts.length; i++) {
                const a = c.cuts[i - 1], b = c.cuts[i], m = (a + b) / 2, p = c.at(m), t = c.tangent(m), length = Math.hypot(...t);
                if (length < 1e-10)
                    continue;
                const start = node(c.at(a)), end = node(c.at(b));
                // Events already identified as the same shared vertex have no edge.
                // Do this before probing a vanishing parameter interval.
                if (start === end)
                    continue;
                // A fixed normal offset can cross a nearby, almost tangent boundary:
                // thin ellipses then acquire a second false edge, or a hidden limb is
                // incorrectly exposed. Bound the probe by clearance to EVERY other
                // analytic curve. sigma_min * |norm(B^-1(p-C))-1| is a conservative
                // distance bound to an ellipse; lines use distance to the finite segment.
                let epsilon = Math.min(.0005, dist(c.at(a), c.at(b)) * .01);
                // Include the opposite half of THIS ellipse. Near a major-axis tip,
                // the normal chord can be far smaller than even its minor axis.
                if (!c.line) {
                    const normal = [-t[1] / length, t[0] / length];
                    const nx = cross2(normal, c.V) / c.det, ny = cross2(c.U, normal) / c.det;
                    const chord = 2 * Math.abs(Math.cos(m) * nx + Math.sin(m) * ny) / (nx * nx + ny * ny);
                    epsilon = Math.min(epsilon, Math.abs(c.det) / c.radius * .05, chord * .2);
                }
                for (const other of curves) {
                    if (other === c)
                        continue;
                    const box = other.box;
                    if (p[0] < box[0] - epsilon || p[0] > box[2] + epsilon || p[1] < box[1] - epsilon || p[1] > box[3] + epsilon)
                        continue;
                    let clearance;
                    if (other.line) {
                        const q = sub(p, other.A), u = Math.max(0, Math.min(1, dot(q, other.D) / dot(other.D, other.D)));
                        clearance = dist(p, other.at(u));
                    }
                    else {
                        const q = sub(p, other.C), x = cross2(q, other.V) / other.det, y = cross2(other.U, q) / other.det;
                        clearance = Math.abs(Math.hypot(x, y) - 1) * Math.abs(other.det) / other.radius;
                    }
                    epsilon = Math.min(epsilon, clearance * .2);
                }
                const n = mul([-t[1], t[0]], epsilon / length), plus = add(p, n), minus = sub(p, n);
                // Never accept a zero/rounded-away side probe as evidence that an edge
                // is absent: an entirely lost region could still form a closed graph.
                if (!(epsilon > 0) || !Number.isFinite(epsilon) || dist(plus, p) === 0 || dist(minus, p) === 0)
                    return null;
                const left = owner(plus), right = owner(minus);
                const segment = { c, a, b, start, end, left, right };
                segments.push(segment);
                for (const raw of silhouettes) {
                    const visible = outlines.get(raw.source), w = raw.world(parameter(raw, p));
                    // Test each physical silhouette independently, including rear spheres
                    // on a shared projected circle. Do not use owner(p)'s strict outside
                    // test ON the limb: roundoff can put p just outside both circles and
                    // thereby incorrectly expose the entire rear silhouette.
                    if (!scene.some(s => s !== raw.source && depthAt(s, w[0], w[1]) > w[2] + .00015)) {
                        if (visible.length && Math.abs(visible.at(-1).b - a) < 1e-9)
                            visible.at(-1).b = b;
                        else
                            visible.push({ c, a, b, start: segment.start, end: segment.end });
                        visible.at(-1).end = segment.end;
                    }
                }
            }
        }
        function commands(s, preview, reverse = false) {
            const c = s.c, a = reverse ? s.b : s.a, b = reverse ? s.a : s.b;
            if (c.line)
                return 'L' + fmt(nodes[reverse ? s.start : s.end]);
            const maxAngle = preview ? Math.min(.2, Math.sqrt(.024 / c.radius)) :
                Math.min(Math.PI / 4, Math.PI / 4 * Math.pow(.001 / (c.radius * 4.3e-6), 1 / 6));
            const count = Math.max(1, Math.ceil(Math.abs(b - a) / maxAngle));
            let text = '';
            for (let i = 1; i <= count; i++) {
                const t0 = a + (b - a) * (i - 1) / count, t1 = a + (b - a) * i / count;
                const end = i === count ? nodes[reverse ? s.start : s.end] : c.at(t1);
                if (preview)
                    text += 'L' + fmt(end);
                else {
                    const k = 4 / 3 * Math.tan((t1 - t0) / 4);
                    text += 'C' + fmt(add(c.at(t0), mul(c.tangent(t0), k))) + ' ' + fmt(sub(c.at(t1), mul(c.tangent(t1), k))) + ' ' + fmt(end);
                }
            }
            return text;
        }
        function directedPath(edges, preview, validateOnly = false) {
            const starts = new Map(), ins = new Map();
            for (const edge of edges) {
                if (!starts.has(edge.start))
                    starts.set(edge.start, []);
                starts.get(edge.start).push(edge);
                ins.set(edge.end, (ins.get(edge.end) || 0) + 1);
            }
            // A numerically ambiguous/tangent junction must never close by a chord.
            // Reject the arrangement and let the proven general path handle it.
            for (const [v, list] of starts)
                if (list.length !== 1 || ins.get(v) !== 1)
                    return null;
            if (ins.size !== starts.size)
                return null;
            if (validateOnly)
                return '';
            const used = new Set();
            let path = '';
            for (const first of edges) {
                if (used.has(first))
                    continue;
                path += 'M' + fmt(nodes[first.start]);
                let edge = first;
                do {
                    if (!edge || used.has(edge))
                        return null;
                    used.add(edge);
                    path += commands(edge.s, preview, edge.reverse);
                    edge = starts.get(edge.end)?.[0];
                } while (edge !== first);
                path += 'Z';
            }
            return path;
        }
        // Keep every primitive's boundary, including white rods and same-color
        // neighbors. Multiple loops remain in one compound path, preserving holes
        // and disconnected components without sampling a full-frame owner map.
        const cachedSurfacePaths = new Map();
        function surfacePaths(preview) {
            if (cachedSurfacePaths.has(preview))
                return cachedSurfacePaths.get(preview);
            cachedSurfacePaths.set(preview, null);
            if (!certifySurfaceOwnership())
                return null;
            const groups = scene.map(() => []);
            for (const s of segments) {
                if (s.left === s.right)
                    continue;
                if (s.left >= 0)
                    groups[s.left].push({ s, reverse: false, start: s.start, end: s.end });
                if (s.right >= 0)
                    groups[s.right].push({ s, reverse: true, start: s.end, end: s.start });
            }
            const paths = scene.map(() => null);
            for (let i = 0; i < groups.length; i++)
                if (groups[i].length) {
                    const path = directedPath(groups[i], preview);
                    if (path === null)
                        return null;
                    paths[i] = path;
                }
            cachedSurfacePaths.set(preview, paths);
            return paths;
        }
        function wash(colorFor, preview, validateOnly = false) {
            const colors = scene.map(s => {
                if (s.kind !== 'sphere')
                    return '';
                let c = colorFor(s.element);
                if (c == null || c === '')
                    return '';
                c = String(c).trim().toLowerCase();
                if (c === 'white' || c === '#fff')
                    c = '#ffffff';
                if (!/^#[0-9a-f]{6}$/.test(c))
                    throw new TypeError('Element colors must be #rrggbb');
                return c === '#ffffff' ? '' : c;
            });
            const groups = new Map();
            for (const s of segments) {
                const left = colors[s.left] || '', right = colors[s.right] || '';
                if (left === right)
                    continue;
                for (const [color, reverse] of [[left, false], [right, true]])
                    if (color) {
                        if (!groups.has(color))
                            groups.set(color, []);
                        groups.get(color).push({ s, reverse, start: reverse ? s.end : s.start, end: reverse ? s.start : s.end });
                    }
            }
            let svg = '<g class="mol-wash" data-boundaries="analytic" stroke="none">';
            for (const [color, edges] of groups) {
                const path = directedPath(edges, preview, validateOnly);
                if (path === null)
                    return null;
                if (validateOnly)
                    continue;
                svg += '<path fill="' + color + '" fill-rule="evenodd" d="' + path + '"/>';
            }
            return svg + '</g>';
        }
        function outline(s, preview, width) {
            if (!width)
                return '';
            return (outlines.get(s) || []).map(segment => '<path stroke-width="' + width.toFixed(3) + '" d="M' + fmt(nodes[segment.start]) + commands(segment, preview) + '"/>').join('');
        }
        // Index geometry by SURFACE identity, not color: white atoms and equal-hue
        // neighbors still have their own visible hatch regions. Build only on use.
        let incident = null;
        function incidentCurves(source) {
            if (!incident) {
                incident = new Map(scene.map(s => [s, new Set()]));
                for (const segment of segments)
                    if (segment.left !== segment.right) {
                        for (const id of [segment.left, segment.right])
                            if (id >= 0)
                                incident.get(scene[id]).add(segment.c);
                    }
            }
            return incident.get(source);
        }
        function intervals(path, cuts, source, front = () => true) {
            cuts.sort((a, b) => a - b);
            cuts = cuts.filter((t, i, a) => !i || t - a[i - 1] > 1e-10);
            const result = [];
            for (let i = 1; i < cuts.length; i++) {
                const a = cuts[i - 1], b = cuts[i], m = (a + b) / 2, p = path.world(m);
                // Physical occlusion, not the legacy .00015 expanded visibility band.
                // Only classify open intervals; boundary endpoints belong to that run.
                if (!front(m) || scene.some(s => s !== source && depthAt(s, p[0], p[1]) > p[2] + 1e-9))
                    continue;
                const lo = a / path.end, hi = b / path.end;
                if (result.length && Math.abs(result.at(-1)[1] - lo) < 1e-10)
                    result.at(-1)[1] = hi;
                else
                    result.push([lo, hi]);
            }
            return result;
        }
        function clipCircle(source, center, u, v) {
            const candidates = incidentCurves(source);
            if (!candidates || source.kind !== 'sphere')
                return null;
            const z = center[2] - source.c[2], amplitude = Math.hypot(u[2], v[2]);
            if (z + amplitude < 0)
                return [];
            const count = curves.length;
            try {
                circle(center, u, v);
                if (curves.length === count)
                    return null;
                const path = curves.pop();
                if (!path || path.line)
                    return null;
                const cuts = [0, TAU];
                // The source limb is cheaper and more stable in 3-D than the double
                // root of the two projected ellipses at a tangent.
                if (amplitude > 0 && Math.abs(z) <= amplitude) {
                    const angle = Math.atan2(v[2], u[2]), half = Math.acos(Math.max(-1, Math.min(1, -z / amplitude)));
                    for (const t of [angle - half, angle + half])
                        cuts.push((t % TAU + TAU) % TAU);
                }
                for (const boundary of candidates)
                    if (!boundary.members.some(m => m.source === source)) {
                        // Plane shortcut is valid only if every shared owner supplies a seam
                        // on this physical sphere; include ALL such planes, not just the first.
                        // Otherwise use the projected shared solver.
                        const contacts = boundary.contacts;
                        if (contacts.length && contacts.length === boundary.members.length && contacts.every(c => c.sphere === source)) {
                            for (const contact of contacts) {
                                // Own sphere/rod seam: reuse its 3-D plane, not a quartic between
                                // projected ellipses. Intersecting a hatch circle with this plane
                                // is just constant + A*cos(t) + B*sin(t) = 0.
                                const k = dot(sub(center, source.c), contact.axis) - contact.offset;
                                const A = dot(u, contact.axis), B = dot(v, contact.axis), r = Math.hypot(A, B);
                                if (r < 1e-14) {
                                    if (Math.abs(k) < 1e-12)
                                        return null;
                                    continue;
                                }
                                if (Math.abs(k) <= r) {
                                    const phase = Math.atan2(B, A), half = Math.acos(Math.max(-1, Math.min(1, -k / r)));
                                    for (const t of [phase - half, phase + half])
                                        cuts.push((t % TAU + TAU) % TAU);
                                }
                            }
                        }
                        else
                            intersections(path, boundary, t => cuts.push(t));
                    }
                return intervals(path, cuts, source, t => z + u[2] * Math.cos(t) + v[2] * Math.sin(t) >= 0);
            }
            catch (_) {
                return null;
            }
            finally {
                curves.length = count;
            }
        }
        function clipLine(source, a, b) {
            if (source.kind !== 'cylinder' || !scene.includes(source))
                return null;
            if (covered.has(source))
                return [];
            const count = curves.length;
            try {
                line2(project(a), project(b));
                if (curves.length === count)
                    return null;
                const path = curves.pop();
                if (!path)
                    return null;
                const direction = sub(b, a);
                path.world = t => add(a, mul(direction, t));
                const cuts = [0, 1];
                for (const boundary of curves) {
                    if (boundary.contacts.length && boundary.contacts.length === boundary.members.length && boundary.contacts.every(c => c.cylinder === source)) {
                        for (const contact of boundary.contacts) {
                            const denominator = dot(direction, contact.axis);
                            if (Math.abs(denominator) > 1e-14) {
                                const t = (contact.offset - dot(sub(a, contact.sphere.c), contact.axis)) / denominator;
                                if (t >= 0 && t <= 1)
                                    cuts.push(t);
                            }
                        }
                    }
                    else
                        intersections(path, boundary, t => cuts.push(t));
                }
                // Same-color cylinder/cylinder contacts are absent from fill boundaries.
                // A generator crossing another closed rod needs its 3-D side/cap events.
                for (const other of cylinders)
                    if (other !== source) {
                        const w = sub(a, other.a), wu = dot(w, other.u), du = dot(direction, other.u);
                        const A = dot(direction, direction) - du * du, B = 2 * (dot(w, direction) - wu * du), C = dot(w, w) - wu * wu - other.r * other.r;
                        const rr = roots([C, B, A], 0, 1);
                        if (rr === null)
                            return null;
                        for (const t of rr) {
                            const axial = wu + t * du;
                            if (axial >= -1e-9 && axial <= other.length + 1e-9)
                                cuts.push(t);
                        }
                        if (Math.abs(du) > 1e-14)
                            for (const end of [0, other.length]) {
                                const t = (end - wu) / du;
                                if (t >= 0 && t <= 1) {
                                    const q = add(w, mul(direction, t));
                                    if (dot(q, q) - end * end <= other.r * other.r + 1e-10)
                                        cuts.push(t);
                                }
                            }
                    }
                return intervals(path, cuts, source);
            }
            catch (_) {
                return null;
            }
            finally {
                curves.length = count;
            }
        }
        let certifiedSurfaceOwnership;
        function certifySurfaceOwnership() {
            if (certifiedSurfaceOwnership !== undefined)
                return certifiedSurfaceOwnership;
            certifiedSurfaceOwnership = false;
            // Fill may merge white rods, but dots need each actual visible surface.
            // Our arrangement omits rod/rod intersection seams. Certify that exposed
            // rod bodies cannot intersect before using it for dot ownership. Trim off
            // the portions proven wholly inside their endpoint balls; bound each
            // remaining body by a capsule and test segment distances conservatively.
            const exposed = cylinders.flatMap((c, i) => {
                if (covered.has(c))
                    return [];
                const lo = Math.sqrt(ends[i][0].r ** 2 - c.r ** 2), hi = c.length - Math.sqrt(ends[i][1].r ** 2 - c.r ** 2);
                return [{ a: add(c.a, mul(c.u, lo)), b: add(c.a, mul(c.u, hi)), r: c.r }];
            });
            const pointSegment = (p, a, b) => { const d = sub(b, a), length2 = dot(d, d), t = length2 ? Math.max(0, Math.min(1, dot(sub(p, a), d) / length2)) : 0; return dist(p, add(a, mul(d, t))); };
            for (let i = 0; i < exposed.length; i++)
                for (let j = 0; j < i; j++) {
                    const x = exposed[i], y = exposed[j], r = x.r + y.r + 1e-8;
                    if ([0, 1, 2].some(k => Math.min(x.a[k], x.b[k]) - Math.max(y.a[k], y.b[k]) > r || Math.min(y.a[k], y.b[k]) - Math.max(x.a[k], x.b[k]) > r))
                        continue;
                    const u = sub(x.b, x.a), v = sub(y.b, y.a), w = sub(x.a, y.a), a = dot(u, u), b = dot(u, v), c = dot(v, v), d = dot(u, w), e = dot(v, w), det = a * c - b * b;
                    // Nearly parallel axes: do not turn cancellation into a false proof.
                    if (det <= 1e-12 * a * c)
                        return false;
                    let distance = Math.min(pointSegment(x.a, y.a, y.b), pointSegment(x.b, y.a, y.b), pointSegment(y.a, x.a, x.b), pointSegment(y.b, x.a, x.b));
                    const s = (b * e - c * d) / det, t = (a * e - b * d) / det;
                    if (s >= 0 && s <= 1 && t >= 0 && t <= 1)
                        distance = Math.min(distance, dist(add(x.a, mul(u, s)), add(y.a, mul(v, t))));
                    if (distance <= r)
                        return false;
                }
            certifiedSurfaceOwnership = true;
            return true;
        }
        let cachedDotRegions;
        function dotRegions() {
            if (cachedDotRegions !== undefined)
                return cachedDotRegions;
            cachedDotRegions = null;
            if (!certifySurfaceOwnership())
                return null;
            const helper = getDotRegions();
            if (helper)
                cachedDotRegions = helper.create(scene, segments, nodes, project, scale);
            return cachedDotRegions;
        }
        return { wash, outline, clipCircle, clipLine, dotRegions, surfacePaths, validate: colorFor => wash(colorFor, true, true) !== null, curveCount: curves.length, segmentCount: segments.length };
    }

    exports.build = build;

    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });

    return exports;

})({});
if (typeof module !== 'undefined' && module.exports) module.exports = MolBoundaries;
