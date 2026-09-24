/* Generated from src/boundaries.ts by npm run build. Edit TypeScript, not this file. */
var MolBoundaries = (function (exports) {
    'use strict';

    const root = globalThis;
    function getDotRegions() {
        return typeof module !== 'undefined' && module.exports ? require('./dot-regions.js') : root.MolDotRegions;
    }

    const TAU = 2 * Math.PI;
    // Numeric policy: these inherited thresholds retain their original values.
    // Unless a formula is explained below, tuning/proof provenance is unknown;
    // names describe use, not an error guarantee. SVG units are projected user
    // coordinates (not necessarily device pixels); world lengths are in Å.
    // Keep shared-helper constants here for consumers that extract this interval.
    const SVG_COORDINATE_DECIMALS = 4;
    // Polynomial coefficients are normalized by their largest magnitude. The
    // root variable is a line fraction or a tan(half-angle) chart coordinate.
    const ROOT_LEADING_COEFFICIENT_TOLERANCE = 1e-13;
    const ROOT_INTERVAL_PADDING = 1e-10, ROOT_RESIDUAL_TOLERANCE = 1e-10;
    const ROOT_BISECTION_STEPS = 48;
    // Carrier equality: relative line angle, SVG offset/center distance, then
    // dimensionless Gram-matrix residual in the other ellipse's local basis.
    const CARRIER_LINE_ANGLE_TOLERANCE = 1e-12, CARRIER_LINE_OFFSET_SVG = 1e-8;
    const CARRIER_CENTER_DISTANCE_SVG = 1e-8, CARRIER_GRAM_TOLERANCE = 1e-11;
    const INTERSECTION_BOX_PADDING_SVG = 1e-6;
    // Mixed parameter units: radians for ellipses, [0,1] fractions for lines.
    const INTERSECTION_PARAMETER_PADDING = 1e-8, INTERSECTION_RESIDUAL_SVG = .00002;
    const LINE_INTERSECTION_DETERMINANT_SVG2 = 1e-10;
    const ELLIPSE_COINCIDENCE_COEFFICIENT_TOLERANCE = 1e-10;
    // Keep the reducer's initial +0 and the original multiply-then-add order.
    const dot = (a, b) => a.length === 2 ? (0 + a[0] * b[0]) + a[1] * b[1] : a.length === 3 ? ((0 + a[0] * b[0]) + a[1] * b[1]) + a[2] * b[2] : a.reduce((v, x, i) => v + x * b[i], 0);
    const add = (a, b) => a.length === 2 ? [a[0] + b[0], a[1] + b[1]] : a.length === 3 ? [a[0] + b[0], a[1] + b[1], a[2] + b[2]] : a.map((x, i) => x + b[i]);
    const mul = (a, k) => a.length === 2 ? [a[0] * k, a[1] * k] : a.length === 3 ? [a[0] * k, a[1] * k, a[2] * k] : a.map(x => x * k);
    const sub = (a, b) => a.length === 2 ? [a[0] + b[0] * -1, a[1] + b[1] * -1] : a.length === 3 ? [a[0] + b[0] * -1, a[1] + b[1] * -1, a[2] + b[2] * -1] : add(a, mul(b, -1));
    const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const norm = (a) => mul(a, 1 / Math.hypot(...a));
    const dist = (a, b) => a.length === 2 ? Math.hypot(a[0] + b[0] * -1, a[1] + b[1] * -1) : a.length === 3 ? Math.hypot(a[0] + b[0] * -1, a[1] + b[1] * -1, a[2] + b[2] * -1) : Math.hypot(...sub(a, b));
    const cross2 = (a, b) => a[0] * b[1] - a[1] * b[0], fmt = (p) => p.map(x => Number(x.toFixed(SVG_COORDINATE_DECIMALS))).join(' ');
    // Isolate real polynomial roots on a bounded interval using derivative roots.
    // Unlike sign-change sampling this also finds double roots (tangent arcs).
    function roots(p, lo, hi) {
        const size = Math.max(...p.map(Math.abs));
        if (!size)
            return null; // coincident curves: caller falls back rather than guessing
        p = p.map(x => x / size);
        while (p.length > 1 && Math.abs(p.at(-1)) < ROOT_LEADING_COEFFICIENT_TOLERANCE)
            p.pop();
        const value = (x) => p.reduceRight((v, c) => v * x + c, 0);
        if (p.length === 1)
            return [];
        if (p.length === 2) {
            const t = -p[0] / p[1];
            return t >= lo - ROOT_INTERVAL_PADDING && t <= hi + ROOT_INTERVAL_PADDING ? [Math.max(lo, Math.min(hi, t))] : [];
        }
        const critical = roots(p.slice(1).map((x, i) => x * (i + 1)), lo, hi) || [];
        const cuts = [lo, ...critical, hi], out = [];
        for (const x of cuts)
            if (Math.abs(value(x)) < ROOT_RESIDUAL_TOLERANCE)
                out.push(x);
        for (let i = 1; i < cuts.length; i++) {
            let a = cuts[i - 1], b = cuts[i], fa = value(a), fb = value(b);
            if (fa * fb >= 0 || Math.abs(fa) < ROOT_RESIDUAL_TOLERANCE || Math.abs(fb) < ROOT_RESIDUAL_TOLERANCE)
                continue;
            for (let j = 0; j < ROOT_BISECTION_STEPS; j++) {
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
            return Math.abs(cross2(a.D, b.D)) <= CARRIER_LINE_ANGLE_TOLERANCE * la * lb &&
                Math.abs(cross2(sub(b.A, a.A), a.D)) <= CARRIER_LINE_OFFSET_SVG * la;
        }
        // Most ellipse pairs have different centers: reject without temporary
        // vectors before the exact near-coincidence check below.
        if (Math.abs(a.C[0] - b.C[0]) > CARRIER_CENTER_DISTANCE_SVG || Math.abs(a.C[1] - b.C[1]) > CARRIER_CENTER_DISTANCE_SVG || dist(a.C, b.C) > CARRIER_CENTER_DISTANCE_SVG)
            return false;
        const U = [cross2(a.U, b.V) / b.det, cross2(b.U, a.U) / b.det];
        const V = [cross2(a.V, b.V) / b.det, cross2(b.U, a.V) / b.det];
        return Math.max(Math.abs(dot(U, U) - 1), Math.abs(dot(V, V) - 1), Math.abs(dot(U, V))) < CARRIER_GRAM_TOLERANCE;
    }
    // Shared projected-curve solver: both the face arrangement and hatch clipping
    // use these intersections. emit receives parameters on a and b respectively.
    function intersections(a, b, emit) {
        if (a.box[0] > b.box[2] + INTERSECTION_BOX_PADDING_SVG || b.box[0] > a.box[2] + INTERSECTION_BOX_PADDING_SVG || a.box[1] > b.box[3] + INTERSECTION_BOX_PADDING_SVG || b.box[1] > a.box[3] + INTERSECTION_BOX_PADDING_SVG)
            return;
        function hit(t) {
            const p = a.at(t), q = parameter(b, p);
            if (q < -INTERSECTION_PARAMETER_PADDING || q > b.end + INTERSECTION_PARAMETER_PADDING || dist(p, b.at(q)) > INTERSECTION_RESIDUAL_SVG)
                return;
            emit(t, Math.max(0, Math.min(b.end, q)));
        }
        if (a.line && b.line) {
            const d = cross2(a.D, b.D);
            if (Math.abs(d) < LINE_INTERSECTION_DETERMINANT_SVG2) {
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
                if (rr === null || Math.max(...poly.map(Math.abs)) < ELLIPSE_COINCIDENCE_COEFFICIENT_TOLERANCE)
                    throw new Error('coincident ellipses');
                for (const t of rr)
                    hit((angle + 2 * Math.atan(t) + TAU) % TAU);
            }
        }
    }
    function build(scene, depthAt, project, scale) {
        // Work budgets / spatial-index performance gates, not geometry tolerances.
        // These are inherited choices, not claims that 64 or 8 is optimal.
        const MAX_SCENE_PRIMITIVES = 200, CLEARANCE_INDEX_MIN_CURVES = 64, CLEARANCE_INDEX_LEAF_CAPACITY = 8;
        // Fast-path input envelope: radii after projection in SVG units; centers
        // (or cylinder starts) in Å. These limits are inherited fallback policy.
        const MAX_PROJECTED_RADIUS_SVG = 10000, MIN_PROJECTED_RADIUS_SVG = .01, MAX_WORLD_COORDINATE_ANGSTROM = 1e4;
        // World-space validation / containment margins (Å), kept separate by role.
        const BOND_ENDPOINT_MATCH_ANGSTROM = 1e-10, SPHERE_TANGENCY_BAND_ANGSTROM = 1e-8;
        const SPHERE_NESTING_MARGIN_ANGSTROM = 1e-8, MIN_SEAM_RADIUS_ANGSTROM = 1e-8;
        const COVERED_ROD_MARGIN_ANGSTROM = 1e-8, INCIDENTAL_CONTACT_MARGIN_ANGSTROM = 1e-8;
        // Relative envelope factor: the literal 1 in the sum supplies an Å baseline.
        const HIDDEN_TANGENT_ENVELOPE_FACTOR = 1e-8;
        // Dimensionless direction checks; basis switch avoids a nearly parallel
        // cross product. Camera guards are inherited legacy-solver thresholds.
        const AXIS_UNIT_SQUARED_TOLERANCE = 1e-10, BASIS_AXIS_SWITCH_COSINE = .95;
        const CAMERA_AXIAL_LOWER_SQUARED = 1e-12, CAMERA_AXIAL_UPPER_SQUARED = 1e-7;
        const GENERATOR_MIN_TRANSVERSE_DIRECTION = 1e-10, OWNER_MIN_TRANSVERSE_SQUARED = 1e-12;
        // Projected degeneracy thresholds: determinant is SVG units squared;
        // determinant/radius and line lengths are SVG units.
        const ELLIPSE_LINE_DETERMINANT_SVG2 = 1e-10, MIN_ELLIPSE_THICKNESS_SVG = .0001;
        const MIN_LINE_LENGTH_SVG = 1e-8, VERTEX_SNAP_SVG = .00002;
        // Curve parameters mix radians (ellipse) and [0,1] fractions (line).
        // Tangent magnitude is correspondingly SVG units per curve parameter.
        const ARRANGEMENT_CUT_PARAMETER_GAP = 1e-9, OUTLINE_JOIN_PARAMETER_GAP = 1e-9;
        const MIN_TANGENT_SVG_PER_PARAMETER = 1e-10;
        // Side probes: absolute SVG cap, then dimensionless fractions of endpoint
        // chord, ellipse thickness, opposite normal chord and other-curve clearance.
        // Fractions are inherited empirical choices; the distance bounds are below.
        const SIDE_PROBE_CAP_SVG = .0005, SIDE_PROBE_ENDPOINT_CHORD_FRACTION = .01;
        const SIDE_PROBE_THICKNESS_FRACTION = .05, SIDE_PROBE_NORMAL_CHORD_FRACTION = .2;
        const SIDE_PROBE_CLEARANCE_FRACTION = .2;
        const OUTLINE_OCCLUSION_BAND_ANGSTROM = .00015;
        // SVG path approximation policy: preview angle cap is radians; its sqrt
        // numerator has SVG units. Cubic coefficient/exponent are inherited fit
        // parameters (dimensionless); no error bound is asserted by these names.
        const PREVIEW_MAX_ANGLE_RADIANS = .2, PREVIEW_ANGLE_RADIUS_FACTOR_SVG = .024;
        const CUBIC_TARGET_ERROR_SVG = .001, CUBIC_ERROR_COEFFICIENT = 4.3e-6, CUBIC_ERROR_POWER = 6;
        const STROKE_WIDTH_DECIMALS = 3;
        // Clipping: raw curve cut gap uses mixed parameters, but output joins use
        // normalized [0,1] fractions. Occlusion is a world depth difference in Å.
        const CLIP_CUT_PARAMETER_GAP = 1e-10, CLIP_JOIN_NORMALIZED_GAP = 1e-10;
        const CLIP_OCCLUSION_DEPTH_ANGSTROM = 1e-9;
        const CONTACT_CIRCLE_MIN_AMPLITUDE_ANGSTROM = 1e-14, CONTACT_PLANE_OFFSET_ANGSTROM = 1e-12;
        const CONTACT_LINE_MIN_DENOMINATOR_ANGSTROM = 1e-14;
        const ROD_SIDE_AXIAL_PADDING_ANGSTROM = 1e-9, ROD_CAP_MIN_AXIAL_DIRECTION_ANGSTROM = 1e-14;
        const ROD_CAP_RADIAL_PADDING_ANGSTROM2 = 1e-10;
        const OWNERSHIP_CAPSULE_MARGIN_ANGSTROM = 1e-8, OWNERSHIP_PARALLEL_RELATIVE_DETERMINANT = 1e-12;
        const spheres = scene.filter((s) => s.kind === 'sphere'), cylinders = scene.filter((s) => s.kind === 'cylinder');
        if (!spheres.length || scene.length > MAX_SCENE_PRIMITIVES || !(scale > 0))
            return null;
        // This fast path proves its geometry assumptions before omitting any curves.
        // Partial sphere intersections contribute their true 3-D seam circles.
        // Degenerate/nested balls, free caps and incidental exposed sphere/rod
        // contacts still use the general path, never a center-sorted drawing.
        if (scene.some(s => !(s.r > 0) || s.r * scale > MAX_PROJECTED_RADIUS_SVG || s.r * scale < MIN_PROJECTED_RADIUS_SVG ||
            (s.kind === 'sphere' ? s.c : s.a).some(x => !Number.isFinite(x) || Math.abs(x) > MAX_WORLD_COORDINATE_ANGSTROM)))
            return null;
        const sphereSeams = [];
        // Near external tangency, a possible sphere/sphere seam lies in a ball
        // about A's point facing B: |seam-contact|² = 2*ra*(ra-h) <= 2*ra*eps.
        // Omit this uncertain seam ONLY if that entire ball is strictly inside a
        // valid connecting finite cylinder. Such points can never be visible owners.
        // Unbonded tangencies, nested balls and all other validation still fail closed.
        function hiddenTangent(a, b, d) {
            const contact = add(a.c, mul(sub(b.c, a.c), a.r / d));
            for (const c of cylinders) {
                if (!(c.r > 0 && c.length > 0) || Math.abs(dot(c.u, c.u) - 1) > AXIS_UNIT_SQUARED_TOLERANCE)
                    continue;
                const end = add(c.a, mul(c.u, c.length));
                if (!((dist(c.a, a.c) < BOND_ENDPOINT_MATCH_ANGSTROM && dist(end, b.c) < BOND_ENDPOINT_MATCH_ANGSTROM) || (dist(c.a, b.c) < BOND_ENDPOINT_MATCH_ANGSTROM && dist(end, a.c) < BOND_ENDPOINT_MATCH_ANGSTROM)))
                    continue;
                const axis = norm(c.u), relative = sub(contact, c.a), t = dot(relative, axis);
                // Deliberately generous world-coordinate error envelope, not a relaxed
                // topology tolerance. Increasing it makes this proof harder to satisfy.
                const margin = HIDDEN_TANGENT_ENVELOPE_FACTOR * (1 + a.r + b.r + c.length + Math.hypot(...a.c) + Math.hypot(...b.c));
                const radius = Math.sqrt(2 * a.r * SPHERE_TANGENCY_BAND_ANGSTROM) + margin;
                const radial = Math.hypot(...sub(relative, mul(axis, t)));
                if (t > radius && c.length - t > radius && radial + radius < c.r)
                    return true;
            }
            return false;
        }
        for (let i = 0; i < spheres.length; i++)
            for (let j = 0; j < i; j++) {
                const a = spheres[i], b = spheres[j], d = dist(a.c, b.c), sum = a.r + b.r;
                if (d > sum + SPHERE_TANGENCY_BAND_ANGSTROM)
                    continue;
                if (d <= Math.abs(a.r - b.r) + SPHERE_NESTING_MARGIN_ANGSTROM)
                    return null;
                if (d >= sum - SPHERE_TANGENCY_BAND_ANGSTROM) {
                    if (hiddenTangent(a, b, d))
                        continue;
                    return null;
                }
                const axis = mul(sub(b.c, a.c), 1 / d), h = (a.r * a.r - b.r * b.r + d * d) / (2 * d);
                const radius = Math.sqrt(a.r * a.r - h * h);
                if (!(radius > MIN_SEAM_RADIUS_ANGSTROM))
                    return null;
                const e = norm(cross(axis, Math.abs(axis[2]) < BASIS_AXIS_SWITCH_COSINE ? [0, 0, 1] : [0, 1, 0])), f = cross(axis, e);
                sphereSeams.push({ center: add(a.c, mul(axis, h)), u: mul(e, radius), v: mul(f, radius) });
            }
        const ends = [], covered = new Set();
        for (const c of cylinders) {
            if (Math.abs(dot(c.u, c.u) - 1) > AXIS_UNIT_SQUARED_TOLERANCE || !(c.length > 0))
                return null;
            const b = add(c.a, mul(c.u, c.length));
            const aSphere = spheres.find(s => dist(s.c, c.a) < BOND_ENDPOINT_MATCH_ANGSTROM), bSphere = spheres.find(s => dist(s.c, b) < BOND_ENDPOINT_MATCH_ANGSTROM);
            if (!aSphere || !bSphere || aSphere === bSphere || c.r >= Math.min(aSphere.r, bSphere.r))
                return null;
            // Legacy ray tolerances become ill-conditioned close to camera-parallel.
            // This guard also precedes covered-carrier omission: mathematical solid
            // containment does not bound the legacy solver's expanded near-axis hits.
            const axial = 1 - c.u[2] * c.u[2];
            if (axial > CAMERA_AXIAL_LOWER_SQUARED && axial < CAMERA_AXIAL_UPPER_SQUARED)
                return null;
            ends.push([aSphere, bSphere]);
            // Every cross-sectional disk is contained in at least one endpoint ball.
            // A strict margin covers endpoint matching/roundoff; retain physical rods
            // in scene (and all raw owner IDs), omit only their invisible carriers.
            if (Math.sqrt(aSphere.r * aSphere.r - c.r * c.r) + Math.sqrt(bSphere.r * bSphere.r - c.r * c.r) > c.length + COVERED_ROD_MARGIN_ANGSTROM) {
                covered.add(c);
                continue;
            }
            for (const s of spheres) {
                if (s === aSphere || s === bSphere)
                    continue;
                const t = Math.max(0, Math.min(c.length, dot(sub(s.c, c.a), c.u)));
                if (dist(s.c, add(c.a, mul(c.u, t))) <= s.r + c.r + INCIDENTAL_CONTACT_MARGIN_ANGSTROM)
                    return null;
            }
        }
        const origin = project([0, 0, 0]), curves = [];
        const vector = (v) => [v[0] * scale, -v[1] * scale];
        function circle(c, u, v, source = null) {
            const C = project(c), U = vector(u), V = vector(v), radius = Math.max(Math.hypot(...u), Math.hypot(...v)) * scale;
            const det = cross2(U, V);
            if (Math.abs(det) < ELLIPSE_LINE_DETERMINANT_SVG2) {
                const axis = norm(Math.hypot(...U) > Math.hypot(...V) ? U : V), half = Math.hypot(dot(U, axis), dot(V, axis));
                line2(sub(C, mul(axis, half)), add(C, mul(axis, half)));
                return;
            }
            if (Math.abs(det) / radius < MIN_ELLIPSE_THICKNESS_SVG)
                throw new Error('ill-conditioned ellipse');
            const extentX = Math.hypot(U[0], V[0]), extentY = Math.hypot(U[1], V[1]);
            const world = (c.length === 3 && u.length === 3 && v.length === 3) ? (t) => {
                const cos = Math.cos(t), sin = Math.sin(t);
                return [c[0] + (u[0] * cos + v[0] * sin), c[1] + (u[1] * cos + v[1] * sin), c[2] + (u[2] * cos + v[2] * sin)];
            } : (t) => add(c, add(mul(u, Math.cos(t)), mul(v, Math.sin(t))));
            curves.push({ C, U, V, det, source, world,
                at: t => { const cos = Math.cos(t), sin = Math.sin(t); return C.length === 2 ? [C[0] + (U[0] * cos + V[0] * sin), C[1] + (U[1] * cos + V[1] * sin)] : add(C, add(mul(U, cos), mul(V, sin))); },
                tangent: t => { const sin = -Math.sin(t), cos = Math.cos(t); return U.length === 2 ? [U[0] * sin + V[0] * cos, U[1] * sin + V[1] * cos] : add(mul(U, sin), mul(V, cos)); },
                cuts: [0, Math.PI / 2, Math.PI, Math.PI * 1.5, TAU], end: TAU, radius,
                box: [C[0] - extentX, C[1] - extentY, C[0] + extentX, C[1] + extentY] });
        }
        function line2(A, B) {
            const D = sub(B, A);
            if (Math.hypot(...D) < MIN_LINE_LENGTH_SVG)
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
                const u = c.u, e = norm(cross(u, Math.abs(u[2]) < BASIS_AXIS_SWITCH_COSINE ? [0, 0, 1] : [0, 1, 0])), f = cross(u, e);
                for (let end = 0; end < 2; end++) {
                    const s = ends[i][end], h = Math.sqrt(s.r * s.r - c.r * c.r);
                    const before = curves.length, offset = end ? -h : h;
                    circle(add(s.c, mul(u, offset)), mul(e, c.r), mul(f, c.r));
                    if (curves.length > before)
                        curves.at(-1).contact = { sphere: s, cylinder: c, axis: u, offset };
                }
                if (Math.hypot(u[0], u[1]) > GENERATOR_MIN_TRANSVERSE_DIRECTION) {
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
        const curveIds = curves.map((_, i) => i);
        function clearanceIndex(ids) {
            const box = [Infinity, Infinity, -Infinity, -Infinity];
            for (const id of ids) {
                const b = curves[id].box;
                box[0] = Math.min(box[0], b[0]);
                box[1] = Math.min(box[1], b[1]);
                box[2] = Math.max(box[2], b[2]);
                box[3] = Math.max(box[3], b[3]);
            }
            if (ids.length <= CLEARANCE_INDEX_LEAF_CAPACITY)
                return { box, ids };
            const axis = box[2] - box[0] >= box[3] - box[1] ? 0 : 1;
            ids.sort((a, b) => curves[a].box[axis] - curves[b].box[axis]);
            const half = ids.length >>> 1;
            return { box, left: clearanceIndex(ids.slice(0, half)), right: clearanceIndex(ids.slice(half)) };
        }
        const clearanceRoot = curves.length > CLEARANCE_INDEX_MIN_CURVES && curves.every(c => c.box.every(Number.isFinite)) ? clearanceIndex(curveIds.slice()) : null;
        function clearanceCandidates(p, epsilon) {
            if (!clearanceRoot || !(epsilon >= 0) || !Number.isFinite(epsilon) || !Number.isFinite(p[0]) || !Number.isFinite(p[1]))
                return curveIds;
            const ids = [];
            function visit(node) {
                const box = node.box;
                // Do not rewrite as p +/- epsilon: reassociation changes rounding at
                // exact boundaries. Enlarging boxes is conservative for this predicate.
                if (p[0] < box[0] - epsilon || p[0] > box[2] + epsilon || p[1] < box[1] - epsilon || p[1] > box[3] + epsilon)
                    return;
                if (node.ids) {
                    for (const id of node.ids) {
                        const b = curves[id].box;
                        if (p[0] < b[0] - epsilon || p[0] > b[2] + epsilon || p[1] < b[1] - epsilon || p[1] > b[3] + epsilon)
                            continue;
                        ids.push(id);
                    }
                }
                else {
                    visit(node.left);
                    visit(node.right);
                }
            }
            visit(clearanceRoot);
            // Epsilon shrinks in original curve order, including ties and degeneracy.
            return ids.sort((a, b) => a - b);
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
                    if (axis2 > OWNER_MIN_TRANSVERSE_SQUARED && perpendicular * perpendicular > shape.r * shape.r * axis2)
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
        const nodes = [], buckets = new Map(), snap = VERTEX_SNAP_SVG;
        function node(p) {
            const x = Math.round(p[0] / snap), y = Math.round(p[1] / snap);
            // Numeric columns avoid nine composite string keys per endpoint. Keep
            // the original dx/dy search order and exact distance/snap predicate.
            for (let dx = -1; dx <= 1; dx++) {
                const column = buckets.get(x + dx);
                if (!column)
                    continue;
                for (let dy = -1; dy <= 1; dy++) {
                    const candidates = column.get(y + dy);
                    if (!candidates)
                        continue;
                    for (const id of candidates)
                        if (dist(nodes[id], p) < snap)
                            return id;
                }
            }
            const id = nodes.length;
            nodes.push(p);
            let column = buckets.get(x);
            if (!column) {
                column = new Map();
                buckets.set(x, column);
            }
            const bucket = column.get(y);
            if (bucket)
                bucket.push(id);
            else
                column.set(y, [id]);
            return id;
        }
        const segments = [], outlines = new Map();
        for (const c of curves) {
            c.cuts.sort((a, b) => a - b);
            c.cuts = c.cuts.filter((t, i, a) => !i || t - a[i - 1] > ARRANGEMENT_CUT_PARAMETER_GAP);
            const silhouettes = c.members.filter(m => m.source);
            for (const raw of silhouettes)
                outlines.set(raw.source, []);
            for (let i = 1; i < c.cuts.length; i++) {
                const a = c.cuts[i - 1], b = c.cuts[i], m = (a + b) / 2, p = c.at(m), t = c.tangent(m), length = Math.hypot(...t);
                if (length < MIN_TANGENT_SVG_PER_PARAMETER)
                    continue;
                const pa = c.at(a), pb = c.at(b), start = node(pa), end = node(pb);
                // Events already identified as the same shared vertex have no edge.
                // Do this before probing a vanishing parameter interval.
                if (start === end)
                    continue;
                // A fixed normal offset can cross a nearby, almost tangent boundary:
                // thin ellipses then acquire a second false edge, or a hidden limb is
                // incorrectly exposed. Bound the probe by clearance to EVERY other
                // analytic curve. sigma_min * |norm(B^-1(p-C))-1| is a conservative
                // distance bound to an ellipse; lines use distance to the finite segment.
                let epsilon = Math.min(SIDE_PROBE_CAP_SVG, dist(pa, pb) * SIDE_PROBE_ENDPOINT_CHORD_FRACTION);
                // Include the opposite half of THIS ellipse. Near a major-axis tip,
                // the normal chord can be far smaller than even its minor axis.
                if (!c.line) {
                    const normal = [-t[1] / length, t[0] / length];
                    const nx = cross2(normal, c.V) / c.det, ny = cross2(c.U, normal) / c.det;
                    const chord = 2 * Math.abs(Math.cos(m) * nx + Math.sin(m) * ny) / (nx * nx + ny * ny);
                    epsilon = Math.min(epsilon, Math.abs(c.det) / c.radius * SIDE_PROBE_THICKNESS_FRACTION, chord * SIDE_PROBE_NORMAL_CHORD_FRACTION);
                }
                let candidates = clearanceCandidates(p, epsilon);
                for (let probe = 0; probe < candidates.length; probe++) {
                    const otherId = candidates[probe], other = curves[otherId];
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
                    epsilon = Math.min(epsilon, clearance * SIDE_PROBE_CLEARANCE_FRACTION);
                    // An invalid clearance can make epsilon NaN; its comparisons then
                    // admit every later curve. Resume the original linear suffix rather
                    // than assume that a non-finite epsilon still only shrinks the query.
                    if (candidates !== curveIds && (!(epsilon >= 0) || !Number.isFinite(epsilon))) {
                        candidates = curveIds;
                        probe = otherId;
                    }
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
                    if (!scene.some(s => s !== raw.source && depthAt(s, w[0], w[1]) > w[2] + OUTLINE_OCCLUSION_BAND_ANGSTROM)) {
                        if (visible.length && Math.abs(visible.at(-1).b - a) < OUTLINE_JOIN_PARAMETER_GAP)
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
            const maxAngle = preview ? Math.min(PREVIEW_MAX_ANGLE_RADIANS, Math.sqrt(PREVIEW_ANGLE_RADIUS_FACTOR_SVG / c.radius)) :
                Math.min(Math.PI / 4, Math.PI / 4 * Math.pow(CUBIC_TARGET_ERROR_SVG / (c.radius * CUBIC_ERROR_COEFFICIENT), 1 / CUBIC_ERROR_POWER));
            const count = Math.max(1, Math.ceil(Math.abs(b - a) / maxAngle));
            let text = '';
            for (let i = 1; i <= count; i++) {
                const t0 = a + (b - a) * (i - 1) / count, t1 = a + (b - a) * i / count;
                const analyticEnd = !preview || i !== count ? c.at(t1) : null;
                const end = i === count ? nodes[reverse ? s.start : s.end] : analyticEnd;
                if (preview)
                    text += 'L' + fmt(end);
                else {
                    const k = 4 / 3 * Math.tan((t1 - t0) / 4);
                    text += 'C' + fmt(add(c.at(t0), mul(c.tangent(t0), k))) + ' ' + fmt(sub(analyticEnd, mul(c.tangent(t1), k))) + ' ' + fmt(end);
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
            return (outlines.get(s) || []).map(segment => '<path stroke-width="' + width.toFixed(STROKE_WIDTH_DECIMALS) + '" d="M' + fmt(nodes[segment.start]) + commands(segment, preview) + '"/>').join('');
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
            cuts = cuts.filter((t, i, a) => !i || t - a[i - 1] > CLIP_CUT_PARAMETER_GAP);
            const result = [];
            for (let i = 1; i < cuts.length; i++) {
                const a = cuts[i - 1], b = cuts[i], m = (a + b) / 2, p = path.world(m);
                // Physical occlusion, not the legacy .00015 expanded visibility band.
                // Only classify open intervals; boundary endpoints belong to that run.
                if (!front(m) || scene.some(s => s !== source && depthAt(s, p[0], p[1]) > p[2] + CLIP_OCCLUSION_DEPTH_ANGSTROM))
                    continue;
                const lo = a / path.end, hi = b / path.end;
                if (result.length && Math.abs(result.at(-1)[1] - lo) < CLIP_JOIN_NORMALIZED_GAP)
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
                                if (r < CONTACT_CIRCLE_MIN_AMPLITUDE_ANGSTROM) {
                                    if (Math.abs(k) < CONTACT_PLANE_OFFSET_ANGSTROM)
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
                            if (Math.abs(denominator) > CONTACT_LINE_MIN_DENOMINATOR_ANGSTROM) {
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
                            if (axial >= -ROD_SIDE_AXIAL_PADDING_ANGSTROM && axial <= other.length + ROD_SIDE_AXIAL_PADDING_ANGSTROM)
                                cuts.push(t);
                        }
                        if (Math.abs(du) > ROD_CAP_MIN_AXIAL_DIRECTION_ANGSTROM)
                            for (const end of [0, other.length]) {
                                const t = (end - wu) / du;
                                if (t >= 0 && t <= 1) {
                                    const q = add(w, mul(direction, t));
                                    if (dot(q, q) - end * end <= other.r * other.r + ROD_CAP_RADIAL_PADDING_ANGSTROM2)
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
                    const x = exposed[i], y = exposed[j], r = x.r + y.r + OWNERSHIP_CAPSULE_MARGIN_ANGSTROM;
                    if ([0, 1, 2].some(k => Math.min(x.a[k], x.b[k]) - Math.max(y.a[k], y.b[k]) > r || Math.min(y.a[k], y.b[k]) - Math.max(x.a[k], x.b[k]) > r))
                        continue;
                    const u = sub(x.b, x.a), v = sub(y.b, y.a), w = sub(x.a, y.a), a = dot(u, u), b = dot(u, v), c = dot(v, v), d = dot(u, w), e = dot(v, w), det = a * c - b * b;
                    // Nearly parallel axes: do not turn cancellation into a false proof.
                    if (det <= OWNERSHIP_PARALLEL_RELATIVE_DETERMINANT * a * c)
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
