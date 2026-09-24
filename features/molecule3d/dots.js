/* Generated from src/dots.ts by npm run build. Edit TypeScript, not this file. */
var MolDots = (function (exports) {
    'use strict';

    const LEVELS = 16;
    const fmt$1 = (n) => String(Number(n.toFixed(4)));
    /** Disk radius / lattice pitch for a desired UNION area (not summed disk area). */
    function halftoneRadiusRatio(coverage) {
        if (coverage <= Math.PI / 4)
            return Math.sqrt(Math.max(0, coverage) / Math.PI);
        if (coverage >= 1)
            return Math.SQRT1_2;
        let lo = .5, hi = Math.SQRT1_2;
        for (let k = 0; k < 24; k++) {
            const r = (lo + hi) / 2, r2 = r * r;
            const area = Math.PI * r2 - 4 * (r2 * Math.acos(.5 / r) - .5 * Math.sqrt(r2 - .25));
            if (area < coverage)
                lo = r;
            else
                hi = r;
        }
        return (lo + hi) / 2;
    }
    /** Exact projected union silhouette, including closed-cylinder caps. All parts
     * in this clipPath are unioned; tone sampling handles front-surface ownership. */
    function projectedSilhouette(scene, project, scale) {
        const parts = [];
        for (const s of scene) {
            const r = s.r * scale;
            if (s.kind === 'sphere') {
                const [x, y] = project(s.c);
                parts.push(`<circle cx="${fmt$1(x)}" cy="${fmt$1(y)}" r="${fmt$1(r)}"/>`);
                continue;
            }
            const a = project(s.a), b = project(s.a.map((v, i) => v + s.u[i] * s.length));
            const dx = b[0] - a[0], dy = b[1] - a[1], length = Math.hypot(dx, dy);
            const vx = length > 1e-12 ? -dy / length : 1, vy = length > 1e-12 ? dx / length : 0;
            const angle = Math.atan2(vy, vx) * 180 / Math.PI;
            for (const p of [a, b])
                parts.push(`<ellipse cx="${fmt$1(p[0])}" cy="${fmt$1(p[1])}" rx="${fmt$1(r)}" ry="${fmt$1(r * Math.abs(s.u[2]))}" transform="rotate(${fmt$1(angle)} ${fmt$1(p[0])} ${fmt$1(p[1])})"/>`);
            if (length > 1e-12) {
                const p = [[a[0] + r * vx, a[1] + r * vy], [b[0] + r * vx, b[1] + r * vy], [b[0] - r * vx, b[1] - r * vy], [a[0] - r * vx, a[1] - r * vy]];
                parts.push(`<path d="M${p.map(v => v.map(fmt$1).join(' ')).join('L')}Z"/>`);
            }
        }
        return parts.join('');
    }
    /** Marching-squares contours of a cumulative tone region. Shared grid edges
     * have shared vertices. Evenodd filling preserves holes/disconnected islands. */
    function contour(values, nx, ny, x0, y0, step, threshold, refine) {
        const nodes = new Map();
        const pairs = [
            [], [[0, 3]], [[0, 1]], [[1, 3]], [[1, 2]], [], [[0, 2]], [[2, 3]],
            [[2, 3]], [[0, 2]], [], [[1, 2]], [[1, 3]], [[0, 1]], [[0, 3]], []
        ];
        for (let y = 0; y < ny - 1; y++)
            for (let x = 0; x < nx - 1; x++) {
                const at = y * nx + x, a = values[at], b = values[at + 1], c = values[at + nx + 1], d = values[at + nx];
                const code = (a >= threshold ? 1 : 0) | (b >= threshold ? 2 : 0) | (c >= threshold ? 4 : 0) | (d >= threshold ? 8 : 0);
                if (code === 0 || code === 15)
                    continue;
                function node(edge) {
                    const vertical = edge === 1 || edge === 3;
                    const start = at + (edge === 1 ? 1 : edge === 2 ? nx : 0), end = start + (vertical ? nx : 1);
                    const id = 2 * start + (vertical ? 1 : 0);
                    if (!nodes.has(id)) {
                        const t = (threshold - values[start]) / (values[end] - values[start]);
                        const a = [x0 + (start % nx) * step, y0 + Math.floor(start / nx) * step];
                        const b = [a[0] + (vertical ? 0 : step), a[1] + (vertical ? step : 0)];
                        const p = refine ? refine(a, b, threshold) : [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
                        nodes.set(id, { p, links: [] });
                    }
                    return id;
                }
                let connections = pairs[code];
                if (code === 5 || code === 10) {
                    const center = (a + b + c + d) / 4 >= threshold;
                    connections = (code === 5 ? center : !center) ? [[0, 1], [2, 3]] : [[0, 3], [1, 2]];
                }
                for (const [first, last] of connections) {
                    const u = node(first), v = node(last);
                    nodes.get(u).links.push(v);
                    nodes.get(v).links.push(u);
                }
            }
        const used = new Set(), paths = [];
        for (const [start] of nodes) {
            if (used.has(start))
                continue;
            const points = [];
            let current = start, previous = -1;
            do {
                if (used.has(current))
                    throw new Error('Open halftone tone contour');
                used.add(current);
                const item = nodes.get(current);
                if (item.links.length !== 2)
                    throw new Error('Invalid halftone tone topology');
                points.push(item.p);
                const next = item.links[0] === previous ? item.links[1] : item.links[0];
                previous = current;
                current = next;
            } while (current !== start);
            if (points.length < 3)
                continue;
            // Remove exactly collinear grid runs, without fitting across sharp shadows.
            const simple = points.filter((p, i) => {
                const a = points[(i + points.length - 1) % points.length], b = points[(i + 1) % points.length];
                return Math.abs((p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0])) > 1e-9;
            });
            if (simple.length >= 3)
                paths.push('M' + simple.map(p => p.map(fmt$1).join(' ')).join('L') + 'Z');
        }
        return paths.join('');
    }
    /** Local numerical fallback for point lights or a BINARY shadow boundary.
     * It never allocates a full-frame ownership/lighting raster. Optional bisection
     * refines hard shadow edges independently of the coarse discovery grid. */
    function sampledTonePaths(bounds, sample, step, thresholds = Array.from({ length: LEVELS }, (_, i) => (i + .5) / LEVELS), refine = false) {
        const [left, top, right, bottom] = bounds;
        if (!(right > left && bottom > top))
            return thresholds.map(() => '');
        step = Math.max(step, Math.sqrt((right - left) * (bottom - top) / 120000), (right - left) / 120000, (bottom - top) / 120000);
        let nx = Math.ceil((right - left) / step) + 3, ny = Math.ceil((bottom - top) / step) + 3;
        while (nx * ny > 130000) {
            step *= 1.1;
            nx = Math.ceil((right - left) / step) + 3;
            ny = Math.ceil((bottom - top) / step) + 3;
        }
        const x0 = left - step, y0 = top - step, values = new Float32Array(nx * ny);
        values.fill(-1);
        const valueAt = (x, y) => { const v = sample(x, y); return v !== null && Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : -1; };
        let maximum = -1;
        for (let y = 1; y < ny - 1; y++)
            for (let x = 1; x < nx - 1; x++) {
                const px = x0 + x * step, py = y0 + y * step;
                if (px > right || py > bottom)
                    continue;
                const value = valueAt(px, py);
                values[y * nx + x] = value;
                maximum = Math.max(maximum, value);
            }
        const refineEdge = refine ? (a, b, threshold) => {
            const inside = valueAt(a[0], a[1]) >= threshold;
            let lo = 0, hi = 1;
            for (let k = 0; k < 9; k++) {
                const t = (lo + hi) / 2;
                if ((valueAt(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) >= threshold) === inside)
                    lo = t;
                else
                    hi = t;
            }
            const t = (lo + hi) / 2;
            return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
        } : undefined;
        return thresholds.map(t => maximum < t ? '' : contour(values, nx, ny, x0, y0, step, t, refineEdge));
    }
    /** Paint precomputed geometric contours with a shared aligned pattern palette. */
    function buildSurfacePatterns(o, emitSurface) {
        const [left, top, right, bottom] = o.bounds;
        if (!(right > left && bottom > top))
            return '';
        const used = new Set();
        let hash1 = 2166136261, hash2 = 5381;
        const hash = (text) => { for (let i = 0; i < text.length; i++) {
            const n = text.charCodeAt(i);
            hash1 = Math.imul(hash1 ^ n, 16777619);
            hash2 = Math.imul(hash2, 33) ^ n;
        } };
        hash(o.bounds.join(',') + ',' + o.pitch + o.silhouette);
        function collect(layer) {
            hash(layer.clip);
            layer.tones.forEach((path, i) => { hash(path); if (path && path !== layer.tones[i + 1])
                used.add(i + 1); });
            if (layer.shadow)
                collect(layer.shadow);
        }
        o.layers.forEach(collect);
        if (!used.size)
            return '';
        const prefix = 'mp-screen-' + (hash1 >>> 0).toString(16) + (hash2 >>> 0).toString(16);
        const defs = [`<clipPath id="${prefix}-surface" clipPathUnits="userSpaceOnUse">${o.silhouette}</clipPath>`];
        for (const level of [...used].sort((a, b) => a - b)) {
            const ink = level / LEVELS, r = o.pitch * halftoneRadiusRatio(ink), dots = [], wrap = r > o.pitch / 2 ? 1 : 0;
            for (let y = -wrap; y <= wrap; y++)
                for (let x = -wrap; x <= wrap; x++)
                    dots.push(`<circle cx="${fmt$1((x + .5) * o.pitch)}" cy="${fmt$1((y + .5) * o.pitch)}" r="${fmt$1(r)}"/>`);
            defs.push(`<pattern id="${prefix}-${level}" data-coverage="${ink}" patternUnits="userSpaceOnUse" patternContentUnits="userSpaceOnUse" x="0" y="0" width="${fmt$1(o.pitch)}" height="${fmt$1(o.pitch)}" patternTransform="rotate(45)" overflow="hidden"><g fill="#161616" stroke="none">${dots.join('')}</g></pattern>`);
        }
        function clip(id, path) { defs.push(`<clipPath id="${id}" clipPathUnits="userSpaceOnUse"><path clip-rule="evenodd" fill-rule="evenodd" d="${path}"/></clipPath>`); }
        function paint(layer, index) {
            const [left, top, right, bottom] = layer.bounds || o.bounds;
            let body = '';
            layer.tones.forEach((path, i) => {
                if (!path || path === layer.tones[i + 1])
                    return;
                const id = prefix + '-tone-' + index + '-' + i;
                clip(id, path);
                body += `<rect data-tone-level="${i + 1}" x="${fmt$1(left)}" y="${fmt$1(top)}" width="${fmt$1(right - left)}" height="${fmt$1(bottom - top)}" fill="url(#${prefix}-${i + 1})" clip-path="url(#${id})"/>`;
            });
            if (layer.shadow)
                body += paint(layer.shadow, index + 's');
            if (body && layer.clip) {
                const id = prefix + '-face-' + index;
                clip(id, layer.clip);
                body = `<g clip-path="url(#${id})">${body}</g>`;
            }
            return body;
        }
        if (emitSurface) {
            for (const [i, layer] of o.layers.entries()) {
                if (layer.sourceId === undefined || !Number.isSafeInteger(layer.sourceId) || layer.sourceId < 0)
                    throw new Error('Per-surface patterns require a primitive sourceId');
                const body = paint(layer, String(i));
                emitSurface(layer.sourceId, `<g data-role="dots" data-mode="halftone" data-renderer="pattern" data-tone-method="${o.method}" data-tone-levels="${LEVELS}" stroke="none"><g clip-path="url(#${prefix}-surface)">${body}</g></g>`);
            }
            return `<defs>${defs.join('')}</defs>`;
        }
        const body = o.layers.map((layer, i) => paint(layer, String(i))).join('');
        return `<g data-role="dots" data-mode="halftone" data-renderer="pattern" data-tone-method="${o.method}" data-tone-levels="${LEVELS}" stroke="none"><defs>${defs.join('')}</defs><g clip-path="url(#${prefix}-surface)">${body}</g></g>`;
    }

    const TAU = 2 * Math.PI;
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const mul = (a, k) => a.map(x => x * k);
    const add = (a, b) => a.map((x, i) => x + b[i]);
    const cross = (a, b) => [
        a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0],
    ];
    const positiveAngle = (t) => ((t % TAU) + TAU) % TAU;
    const clamp$1 = (x) => Math.max(-1, Math.min(1, x));
    const fmt = (p) => `${p[0].toFixed(4)} ${p[1].toFixed(4)}`;
    /** Affine (orthographic) projection preserves these circle/ellipse controls. */
    function ellipse(project, center, u, v) {
        const c = project(center), pu = project(add(center, u)), pv = project(add(center, v));
        const U = [pu[0] - c[0], pu[1] - c[1]], V = [pv[0] - c[0], pv[1] - c[1]];
        return {
            at: t => [c[0] + U[0] * Math.cos(t) + V[0] * Math.sin(t),
                c[1] + U[1] * Math.cos(t) + V[1] * Math.sin(t)],
            tangent: t => [-U[0] * Math.sin(t) + V[0] * Math.cos(t),
                -U[1] * Math.sin(t) + V[1] * Math.cos(t)],
        };
    }
    /** Optional anchors make adjoining carriers use identical intersection points. */
    function arc(e, start, end, first, last) {
        const count = Math.max(1, Math.ceil(Math.abs(end - start) / (Math.PI / 4)));
        const step = (end - start) / count, k = 4 / 3 * Math.tan(step / 4);
        let out = '', p = first ?? e.at(start);
        for (let i = 0; i < count; i++) {
            const a = start + i * step, b = i === count - 1 ? end : start + (i + 1) * step;
            const q = i === count - 1 && last ? last : e.at(b);
            const da = e.tangent(a), db = e.tangent(b);
            out += `C${fmt([p[0] + k * da[0], p[1] + k * da[1]])} ${fmt([q[0] - k * db[0], q[1] - k * db[1]])} ${fmt(q)}`;
            p = q;
        }
        return out;
    }
    function full(e) {
        const p = e.at(0);
        return `M${fmt(p)}${arc(e, 0, TAU, p, p)}Z`;
    }
    /**
     * Closed analytic directional-light tone boundaries, for SVG fill-rule="evenodd".
     * Coordinates/normals are in view space (+z faces the viewer); project must be
     * affine/orthographic. Occlusion is deliberately left to the caller's clip path.
     * Circular arcs use standard cubic approximations spanning at most pi/4.
     * A zero/nonfinite light or NaN threshold produces an empty path.
     */
    function directionalTonePath(s, project, light, threshold) {
        const lightLength = Math.hypot(light[0], light[1], light[2]);
        if (!(lightLength > 0) || !Number.isFinite(lightLength) || Number.isNaN(threshold) || !(s.r > 0))
            return '';
        const L = mul(light, 1 / lightLength), T = threshold;
        if (s.kind === 'sphere') {
            if (T <= -1)
                return '';
            const rim = ellipse(project, s.c, [s.r, 0, 0], [0, s.r, 0]);
            if (T >= 1)
                return full(rim);
            const h = Math.hypot(L[0], L[1]), q = Math.sqrt((1 - T) * (1 + T));
            const e = h > 0 ? [-L[1] / h, L[0] / h, 0] : [1, 0, 0];
            const f = cross(L, e);
            const iso = ellipse(project, add(s.c, mul(L, s.r * T)), mul(e, s.r * q), mul(f, s.r * q));
            // Axial T=0 has coincident rim/isocircle: do not XOR the rim with itself.
            if (h === 0) {
                if (L[2] > 0)
                    return T <= 0 ? '' : full(rim) + full(iso);
                return T >= 0 ? full(rim) : full(iso);
            }
            if (Math.abs(T) < h) {
                const phi = Math.atan2(L[1], L[0]), alpha = Math.acos(clamp$1(T / h));
                // This increasing equator arc contains phi+pi, the darkest rim point.
                const a = phi + alpha, b = phi + TAU - alpha;
                const n0 = [Math.cos(a), Math.sin(a), 0], n1 = [Math.cos(b), Math.sin(b), 0];
                const p0 = project(add(s.c, mul(n0, s.r))), p1 = project(add(s.c, mul(n1, s.r)));
                // n dot e/f = q cos/sin(t); the center T*L is perpendicular to e/f.
                const t0 = Math.atan2(dot(n1, f), dot(n1, e));
                const t1 = Math.atan2(dot(n0, f), dot(n0, e));
                let sweep = positiveAngle(t1 - t0);
                const mid = t0 + sweep / 2;
                if (T * L[2] + q * (e[2] * Math.cos(mid) + f[2] * Math.sin(mid)) < 0)
                    sweep -= TAU;
                return `M${fmt(p0)}${arc(rim, a, b, p0, p1)}${arc(iso, t0, t0 + sweep, p1, p0)}Z`;
            }
            // No transverse crossings (including tangency): each entire boundary is
            // either eligible or hidden. Center z decides frontness here; using it
            // avoids cancellation in min-z at a tangent. Evenodd gives holes or caps.
            let out = T >= h ? full(rim) : '';
            if (T * L[2] > 0)
                out += full(iso);
            return out;
        }
        // Primitive cylinder axes are unit vectors, as required by the scene model.
        const u = s.u, h = Math.hypot(u[0], u[1]);
        const e = h > 0 ? [-u[1] / h, u[0] / h, 0] : [1, 0, 0];
        const f = cross(u, e), b = add(s.a, mul(u, s.length));
        const ca = ellipse(project, s.a, mul(e, s.r), mul(f, s.r));
        const cb = ellipse(project, b, mul(e, s.r), mul(f, s.r));
        let out = '';
        if (h > 0 && s.length > 0) {
            // f.z=h, so precisely theta in [0,pi] faces the viewer.
            const A = dot(e, L), B = dot(f, L), R = Math.hypot(A, B);
            const cuts = [0, Math.PI];
            if (R > 0 && Math.abs(T) < R) {
                const phase = Math.atan2(B, A), delta = Math.acos(clamp$1(T / R));
                for (const base of [phase - delta, phase + delta]) {
                    const t = positiveAngle(base);
                    if (t > 0 && t < Math.PI)
                        cuts.push(t);
                }
            }
            // A tangent root does not change interval eligibility and needs no split.
            cuts.sort((x, y) => x - y);
            for (let i = 1; i < cuts.length; i++) {
                const t0 = cuts[i - 1], t1 = cuts[i], mid = (t0 + t1) / 2;
                if (!(t1 > t0) || A * Math.cos(mid) + B * Math.sin(mid) > T)
                    continue;
                // At an exact minimum, only a generator is eligible (zero filled area).
                if (R > 0 && T <= -R)
                    continue;
                const a0 = ca.at(t0), b0 = cb.at(t0), b1 = cb.at(t1), a1 = ca.at(t1);
                out += `M${fmt(a0)}L${fmt(b0)}${arc(cb, t0, t1, b0, b1)}L${fmt(a1)}${arc(ca, t1, t0, a1, a0)}Z`;
            }
        }
        // End-on cylinders intentionally contribute only the visible planar cap.
        const axialLight = dot(u, L);
        if (u[2] > 0 && axialLight <= T)
            out += full(cb);
        if (u[2] < 0 && -axialLight <= T)
            out += full(ca);
        return out;
    }

    const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
    function hash(x, y, salt) {
        let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(salt, 1274126177);
        h = Math.imul(h ^ (h >>> 13), 1274126177);
        return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
    }
    function buildDots(scene, depthAt, project, scale, illumination, options, regions = null, referenceCoverage, surfaces) {
        const o = { shadingMode: 'stipple', dotSpacing: 2.5, dotSize: .5, dotContrast: 1.2, ...options };
        if (!['stipple', 'halftone'].includes(o.shadingMode))
            throw new Error('Invalid dot mode');
        if (!Number.isFinite(o.dotSpacing) || o.dotSpacing < .3 || o.dotSpacing > 19 || !Number.isFinite(o.dotSize) || o.dotSize < 0 || o.dotSize > 4 || !Number.isFinite(o.dotContrast) || o.dotContrast < .5 || o.dotContrast > 2.5)
            throw new Error('Invalid dot settings');
        if (!(scale > 0) || !Number.isFinite(scale))
            throw new Error('Invalid scale');
        if (o.dotSize === 0 || scene.length === 0)
            return '';
        const origin = project([0, 0, 0]), g = o.dotSpacing;
        const maxRadius = o.dotSize;
        const fineScale = Math.min(1, o.dotSize), minRadius = .03 * fineScale;
        const shapes = scene.map((s, id) => {
            const a = project(s.kind === 'sphere' ? s.c : s.a);
            const b = s.kind === 'sphere' ? a : project(s.a.map((v, i) => v + s.u[i] * s.length));
            const r = s.r * scale;
            return { s, id, b: [Math.min(a[0], b[0]) - r, Math.min(a[1], b[1]) - r, Math.max(a[0], b[0]) + r, Math.max(a[1], b[1]) + r] };
        });
        const minX = Math.min(...shapes.map(s => s.b[0])), minY = Math.min(...shapes.map(s => s.b[1]));
        const maxX = Math.max(...shapes.map(s => s.b[2])), maxY = Math.max(...shapes.map(s => s.b[3]));
        function hit(x, y, queryRadius = maxRadius * 1.03) {
            const wx = (x - origin[0]) / scale, wy = (origin[1] - y) / scale;
            if (regions && o.shadingMode !== 'halftone') {
                // Visibility/occlusion is already solved. The one surface intersection
                // below only reconstructs this known owner's position for its normal.
                const region = regions.query(x, y, queryRadius);
                if (!region)
                    return null;
                const s = scene[region.id], z = depthAt(s, wx, wy);
                return Number.isFinite(z) ? { id: region.id, s, p: [wx, wy, z], clearance: region.clearance } : null;
            }
            let best = -Infinity, item = null;
            for (const shape of shapes) {
                const b = shape.b;
                if (x < b[0] || y < b[1] || x > b[2] || y > b[3])
                    continue;
                const z = depthAt(shape.s, wx, wy);
                if (Number.isFinite(z) && z > best) {
                    best = z;
                    item = shape;
                }
            }
            return item ? { id: item.id, s: item.s, p: [wx, wy, best] } : null;
        }
        function normal(h) {
            const s = h.s, p = h.p;
            if (s.kind === 'sphere')
                return p.map((v, i) => (v - s.c[i]) / s.r);
            const q = p.map((v, i) => v - s.a[i]), t = q.reduce((sum, v, i) => sum + v * s.u[i], 0);
            if (t < 1e-7)
                return s.u.map(v => -v);
            if (t > s.length - 1e-7)
                return s.u.slice();
            const radial = q.map((v, i) => v - t * s.u[i]), length = Math.hypot(...radial);
            return length ? radial.map(v => v / length) : [0, 0, 1];
        }
        const dirs = Array.from({ length: 16 }, (_, i) => [Math.cos(i * Math.PI / 8), Math.sin(i * Math.PI / 8)]);
        function safeRadius(x, y, r, owner) {
            // The whole sampled disk must stay on the same visible primitive, not
            // merely its center. Shrink at silhouettes and occlusion boundaries.
            // Two rings are a numerical footprint test, not an exact curve boolean.
            function fits(radius) {
                for (const k of [.5, 1])
                    for (const d of dirs) {
                        const h = hit(x + d[0] * radius * k, y + d[1] * radius * k);
                        if (!h || h.id !== owner)
                            return false;
                    }
                return true;
            }
            if (fits(r))
                return r;
            let lo = 0, hi = r;
            for (let i = 0; i < 9; i++) {
                const mid = (lo + hi) / 2;
                if (fits(mid))
                    lo = mid;
                else
                    hi = mid;
            }
            return lo;
        }
        // Normalize the MEAN, never the spatial pattern of the reference hatches.
        // Local tone depends only on smooth illumination, not line direction,
        // projected crowding, or the thresholds that turn hatch families on/off.
        const exponent = referenceCoverage ? o.dotContrast / 1.2 : o.dotContrast;
        const smoothTone = (lit) => Math.pow(clamp((1 - lit) / 2, 0, 1), exponent);
        const surfaceIllumination = surfaces?.illumination;
        const lightAt = (h, n) => surfaceIllumination ? surfaceIllumination(h.s, n, h.p) : illumination(n, h.p);
        let toneGain = 1;
        if (referenceCoverage) {
            const left = o.width === undefined ? minX : Math.max(0, minX), right = o.width === undefined ? maxX : Math.min(o.width, maxX);
            const top = o.height === undefined ? minY : Math.max(0, minY), bottom = o.height === undefined ? maxY : Math.min(o.height, maxY);
            const step = Math.max(2, (right - left) / 128, (bottom - top) / 128), tones = [];
            let target = 0;
            for (let y = top + .61 * step; y < bottom; y += step)
                for (let x = left + .37 * step; x < right; x += step) {
                    const h = hit(x, y);
                    if (!h)
                        continue;
                    const n = normal(h), lit = clamp(lightAt(h, n), -1, 1);
                    tones.push(smoothTone(lit));
                    target += clamp(referenceCoverage(h.s, n, lit), 0, 1);
                }
            const total = (gain) => tones.reduce((sum, t) => sum + Math.min(1, gain * t), 0);
            if (target === 0)
                toneGain = 0;
            else if (tones.length) {
                let lo = 0, hi = 1;
                while (hi < 1048576 && total(hi) < target)
                    hi *= 2;
                for (let i = 0; i < 24; i++) {
                    const mid = (lo + hi) / 2;
                    if (total(mid) < target)
                        lo = mid;
                    else
                        hi = mid;
                }
                toneGain = (lo + hi) / 2;
            }
        }
        function coverage(h) {
            const lit = clamp(lightAt(h, normal(h)), -1, 1);
            return clamp(toneGain * smoothTone(lit), 0, 1);
        }
        if (o.shadingMode === 'halftone') {
            if (toneGain === 0)
                return '';
            const bounds = [
                o.width === undefined ? minX : Math.max(0, minX), o.height === undefined ? minY : Math.max(0, minY),
                o.width === undefined ? maxX : Math.min(o.width, maxX), o.height === undefined ? maxY : Math.min(o.height, maxY)
            ];
            const layers = [];
            const thresholds = Array.from({ length: 16 }, (_, i) => (i + .5) / 16), brightness = o.shadingBrightness ?? 0;
            const step = o.quality === 'preview' ? 2 : 1;
            for (const { s, id, b } of shapes) {
                if (surfaces?.paths && !surfaces.paths[id])
                    continue;
                const visiblePath = surfaces?.paths?.[id] || '';
                const box = [Math.max(bounds[0], b[0]), Math.max(bounds[1], b[1]), Math.min(bounds[2], b[2]), Math.min(bounds[3], b[3])];
                // Exact visible paths' Bezier control hulls conservatively bound the
                // local work. Hidden surfaces and hidden parts need no tone sampling.
                if (visiblePath) {
                    const coords = (visiblePath.match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi) || []).map(Number);
                    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
                    for (let i = 0; i < coords.length; i += 2) {
                        x0 = Math.min(x0, coords[i]);
                        x1 = Math.max(x1, coords[i]);
                        y0 = Math.min(y0, coords[i + 1]);
                        y1 = Math.max(y1, coords[i + 1]);
                    }
                    box[0] = Math.max(box[0], x0);
                    box[1] = Math.max(box[1], y0);
                    box[2] = Math.min(box[2], x1);
                    box[3] = Math.min(box[3], y1);
                }
                if (!(box[2] > box[0] && box[3] > box[1]))
                    continue;
                const onSurface = (x, y) => {
                    if (!visiblePath) {
                        const h = hit(x, y);
                        return h?.id === id ? h : null;
                    }
                    const wx = (x - origin[0]) / scale, wy = (origin[1] - y) / scale, z = depthAt(s, wx, wy);
                    return Number.isFinite(z) ? { id, s, p: [wx, wy, z] } : null;
                };
                if (surfaces?.light && visiblePath) {
                    const light = surfaces.light;
                    const threshold = (ink) => 1 - 2 * Math.pow(ink / toneGain, 1 / exponent) - 2 * brightness;
                    const layer = { sourceId: id, clip: visiblePath, bounds: box, tones: thresholds.map(t => t > toneGain ? '' : directionalTonePath(s, project, light, threshold(t))) };
                    // Only one binary shadow contour is sampled locally. Its shaded tone
                    // boundaries remain analytic, with the shadow attenuation inverted.
                    if (surfaces.shadowed && surfaces.mayShadow?.[id]) {
                        const shadowed = surfaces.shadowed;
                        const mask = sampledTonePaths(box, (x, y) => { const h = onSurface(x, y); return h && shadowed(id, normal(h), h.p) ? 1 : 0; }, step, [.5], true)[0];
                        if (mask) {
                            const strength = o.shadowStrength ?? .8;
                            const constant = clamp(toneGain * smoothTone(clamp(-1 + 2 * brightness, -1, 1)), 0, 1);
                            layer.shadow = { sourceId: id, clip: mask, bounds: box, tones: thresholds.map(t => {
                                    if (strength >= 1)
                                        return constant >= t ? visiblePath : '';
                                    return t > toneGain ? '' : directionalTonePath(s, project, light, (threshold(t) + 1) / (1 - strength) - 1);
                                }) };
                        }
                    }
                    layers.push(layer);
                }
                else {
                    // Point-light attenuation, unsupported visibility arrangements, and
                    // custom low-level light callbacks stay local to each primitive.
                    layers.push({ sourceId: id, clip: visiblePath, bounds: box, tones: sampledTonePaths(box, (x, y) => { const h = onSurface(x, y); return h ? coverage(h) : null; }, step) });
                }
            }
            return buildSurfacePatterns({ bounds, pitch: g * Math.SQRT2 / 5, silhouette: projectedSilhouette(scene, project, scale), layers,
                method: surfaces?.paths ? (surfaces.light ? (surfaces.shadowed ? 'analytic-local-shadows' : 'analytic') : 'surface-sampled') : 'local-fallback' }, surfaces?.emitSurface);
        }
        const circles = [], batches = surfaces?.compactStipple ? new Map() : null;
        const emitSurface = surfaces?.emitSurface;
        const owners = new Map();
        let markCount = 0;
        function emit(x, y, certifiedCell = false, cellOwner = -1) {
            if (x < minX || y < minY || x > maxX || y > maxY)
                return;
            const h = certifiedCell ? null : hit(x, y);
            if (!certifiedCell && !h)
                return;
            let radius = o.dotSize;
            if (radius < minRadius)
                return;
            // Contract only near actual boundaries, not every interior mark: a global
            // radius contraction would silently reduce the calibrated coverage.
            const clearance = certifiedCell ? maxRadius * 1.03 : regions ? h.clearance : safeRadius(x, y, radius * 1.03, h.id);
            radius = Math.floor(Math.min(radius, Math.max(0, clearance * Math.cos(Math.PI / 16) - .003 * fineScale)) * 1000) / 1000;
            if (radius < minRadius)
                return;
            markCount++;
            let targetCircles = circles, targetBatches = batches;
            if (emitSurface) {
                const owner = certifiedCell ? cellOwner : h.id;
                let target = owners.get(owner);
                if (!target) {
                    target = { circles: [], batches: batches ? new Map() : null };
                    owners.set(owner, target);
                }
                targetCircles = target.circles;
                targetBatches = target.batches;
            }
            if (targetBatches) {
                let batch = targetBatches.get(radius);
                if (!batch) {
                    batch = [];
                    targetBatches.set(radius, batch);
                }
                batch.push(`M${x.toFixed(3)} ${y.toFixed(3)}h0`);
            }
            else
                targetCircles.push(`<circle cx="${x.toFixed(3)}" cy="${y.toFixed(3)}" r="${radius.toFixed(3)}"/>`);
        }
        if (o.shadingMode === 'stipple' && toneGain > 0) {
            // Certify a whole candidate cell plus its largest disk once. Interior
            // Poisson marks then need neither owner/depth nor boundary-distance queries.
            const cellRadius = Math.SQRT1_2 * g + maxRadius * 1.03;
            const i0 = Math.floor(minX / g) - 1, i1 = Math.ceil(maxX / g) + 1, j0 = Math.floor(minY / g) - 1, j1 = Math.ceil(maxY / g) + 1;
            if ((i1 - i0 + 1) * (j1 - j0 + 1) > 1000000)
                throw new Error('Dot screen too large; increase spacing or reduce output size');
            for (let j = j0; j <= j1; j++)
                for (let i = i0; i <= i1; i++) {
                    const h = hit((i + .5) * g, (j + .5) * g, regions ? cellRadius : maxRadius * 1.03);
                    if (!h)
                        continue;
                    const certifiedCell = !!regions && h.clearance >= cellRadius - 1e-12;
                    // Equal-radius Poisson marks. Account for overlap using
                    // coverage = 1-exp(-numberDensity * diskArea), rather than adding areas.
                    const ink = Math.min(.995, coverage(h));
                    if (ink <= 0)
                        continue;
                    const mean = -Math.log1p(-ink) * g * g / (Math.PI * o.dotSize * o.dotSize);
                    if (mean > 1000)
                        throw new Error('Stipple density too high; increase dot size');
                    const stop = Math.exp(-mean);
                    let product = 1, count = 0;
                    while ((product *= 1 - hash(i, j, 100 + count)) > stop)
                        count++;
                    for (let k = 0; k < count; k++) {
                        emit((i + hash(i, j, 10000 + 2 * k)) * g, (j + hash(i, j, 10001 + 2 * k)) * g, certifiedCell, h.id);
                        if (markCount > 1000000)
                            throw new Error('Too many stipple marks; use a coarser texture');
                    }
                }
        }
        // SVG round caps on zero-length subpaths are exact disks. This batches
        // serialization/DOM nodes, not positions: there is no tile or repeated motif.
        if (emitSurface) {
            for (const [id, target] of owners) {
                if (target.batches)
                    for (const [r, points] of target.batches)
                        target.circles.push(`<path data-stipple-radius="${r.toFixed(3)}" fill="none" stroke="#161616" stroke-width="${(2 * r).toFixed(3)}" stroke-linecap="round" d="${points.join('')}"/>`);
                emitSurface(id, `<g data-role="dots" data-mode="stipple" fill="#161616" stroke="none">${target.circles.join('')}</g>`);
            }
            return '';
        }
        if (batches)
            for (const [r, points] of batches)
                circles.push(`<path data-stipple-radius="${r.toFixed(3)}" fill="none" stroke="#161616" stroke-width="${(2 * r).toFixed(3)}" stroke-linecap="round" d="${points.join('')}"/>`);
        return `<g data-role="dots" data-mode="${o.shadingMode}" fill="#161616" stroke="none">${circles.join('')}</g>`;
    }

    exports.buildDots = buildDots;

    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });

    return exports;

})({});
if (typeof module !== 'undefined' && module.exports) module.exports = MolDots;
