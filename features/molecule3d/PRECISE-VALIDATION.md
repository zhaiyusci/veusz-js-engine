# Precise rendering enabled — adapter 0.3.0

Historical record. Version 0.3.1 corrects the mistaken forced-vector-stipple policy
and restores upstream bitmap textures; see [BITMAP-VALIDATION.md](BITMAP-VALIDATION.md).
The marks timings below do not measure the current bitmap path.

## Behavior

The existing pinned MolecularRenaissance scripts (`7b93c9b`) were not modified.
`molecule3d` now defaults to `renderMode='precise'`; `fast` remains selectable in
Formatting -> View. Both modes use export-quality paths, shared quantized shading
and vector stipple marks.

Lighting adds `castShadows` (initially false) and `shadowStrength` (initially 0.8,
range 0..1). Precise mode can use directional cast shadows. Fast mode suppresses
their effect but preserves the saved switch/strength, so switching back restores
them. Point-light options remain removed upstream.

All new fields are flat native settings. Existing documents without a renderMode
field now use precise. Explicitly save `renderMode='fast'` for the approximate
painter-order geometry. Old scale, radius multiplier, orientation, label/font and
placement settings are unchanged. Restart Veusz to rebuild the feature runtime
and settings interface.

## Necessary transparent-background adaptation

The first full precise regression exposed a real rendering problem, not merely
an obsolete test: upstream non-hatch rendering without labels or element textures
can omit opaque white atom/bond fills and rely on its white canvas rectangle.
Removing that rectangle for Veusz made those molecular interiors transparent.
The existing pixel test correctly detected zero paper-white interior pixels.

For this pinned API the adapter now requests upstream's label-enabled certified
owner layers in precise mode. Those layers include white atom/bond bodies even
when color wash is off. User-disabled labels are stripped before Qt adaptation;
this does not enable visible text or request Qt glyph measurements. The adapter
keeps upstream's actual visibility paths, not approximated circles or fast-mode
substitution. If certified surface fills are unavailable, it returns a visible,
nonfatal error suggesting explicit fast mode. It does not silently render hollow
atoms or switch geometry modes.

The clip-to-mask and zero-length-stipple-to-circle compatibility steps remain.
The Qt silhouette thresholds were not relaxed. Precise labels can legitimately
omit atoms whose label anchor is occluded.

## Executed regression results

Windows, real Qt against the sibling upstream Veusz checkout:

| Backend | Feature suite | Native formatting suite |
|---|---:|---:|
| Firefox | 28 passed, 77.360 s | 13 passed, 21.218 s |
| Explicit QuickJS | 28 passed, 53.208 s | 13 passed, 2.159 s |

These are full suite wall times, **not renderer speed comparisons**: they include
browser startup per case, Python pixel loops, Qt painting, export and native UI.
Suites ran sequentially to avoid shared export-fixture races.

New coverage includes:

- Precise is the default, including requests/documents missing the new fields.
- Mode/shadow option types/ranges, forced export quality and vector mark delivery.
- Same-axis overlapping atoms: front color, rear visible ring, hidden rear label,
  and invariance of actual pixels when XYZ atom order is reversed.
- Real shadow pixel changes, zero-strength recovery, fast-mode shadow suppression,
  and switching/cache restoration. Inactive strength changes can alter generated
  SVG IDs; this assertion compares rendered pixels rather than ID strings.
- White H atoms and their connecting bond remain opaque in label-free stipple and
  halftone output; no text or font measurement leaks from internal owner requests.
- Missing certified surfaces produce visible errors and recover after correction.
- All five halftone levels remain confined to the physical sphere silhouette;
  unchanged light/dark ink thresholds and no outside leakage.
- The 60-sample common-coverage halftone plateau regression still has max level-count
  ink drift 0.0. This is not a claim of absolute ink calibration or browser/Qt
  raster equivalence.
- Native mode/shadow controls, edit/undo/reset, saved shadow state while fast,
  flat-path save/load, the six-widget example, and document SVG/PNG export.

Four legacy geometry tests explicitly retain fast mode because they assert its
full-circle or all-atom-label representation. The remaining default rendering
cases and the new visibility/shadow tests exercise precise, rather than moving
the whole suite back to fast.

## Frozen Veusz

Actual `C:\Program Files\Veusz\veusz.exe` four-feature SVG/PNG export passed with
the final adapter under:

- Firefox browser backend;
- Edge browser backend;
- explicit QuickJS backend.

Reports are generated under `build-test-browser-veusz/{browser-firefox,
browser-msedge,quickjs-firefox}/results.json`. Native View/Lighting screenshots and
the six-widget export were visually inspected. No user preferences, sibling
Veusz source files, browser backend timeouts or process ownership code changed.

## Raw browser renderer probe

A separate Firefox Worker loaded the five exact vendor scripts and rendered 27
cases: water/ethanol/C60 x hatch/stipple/halftone x precise without shadows / fast
without shadows / precise with shadows. All completed. Settings: 600x500 SVG,
24 SVG units/angstrom (18 pt/angstrom), radius multiplier 0.75, 16 shading levels,
vector stipple, labels enabled, pitch -10 degrees, yaw 15 degrees.

Single-pass JS `performance.now()` measurements in one session (no statistical
benchmark; JIT/order/timer granularity matter):

| Model | Precise hatch, shadows off/on | Precise stipple, off/on | Precise halftone, off/on |
|---|---:|---:|---:|
| Water | 11 / 6 ms | 10 / 8 ms | 4 / 6 ms |
| Ethanol | 6 / 11 ms | 10 / 13 ms | 7 / 8 ms |
| C60 | 75 / 101 ms | 100 / 127 ms | 82 / 112 ms |

C60 fast measurements were 73/150/67 ms for hatch/stipple/halftone. They are not a
universal ordering guarantee: fast is an approximation strategy, not necessarily
faster for every style or warmed-up sample. Precise C60 hatch emitted about
2.26 MB without shadows and 3.11 MB with shadows. Transmission, Qt glyph outlining,
mask rasterization and document export are excluded from these JS timings.

The probe used a private 60-second request ceiling; production retains its
existing default. No measured case came close to that limit. Probe script/raw
SVGs/results are generated under `build-test-molecule3d-precise/`.

## Failures addressed and limits

- The initial sandbox probe could not create Firefox's profile; an approved parent
  rerun succeeded. No alternate profile-access workaround was used.
- Initial precise tests exposed missing white fills. The adapter was fixed as
  above, with additional alpha/white-interior tests; no pixel tolerance reduction.
- A fast-mode test initially compared SVG text despite option-dependent IDs.
  It now verifies actual image identity for ineffective shadow settings.
- One combined PowerShell smoke invocation stopped after Firefox because a script
  call did not set LASTEXITCODE. Edge and QuickJS were subsequently run explicitly
  under terminating-error handling and both passed; their runs were not inferred
  from the earlier exit code.
- Existing user-site `_distutils_hack`, optional astropy/SAMP and upstream Python
  deprecation notices appeared but did not fail the final runs.

Qt may still rasterize masks/pattern tiles in its final SVG export. Large or
uncertifiable custom geometries can fail the existing size/geometry limits;
explicit fast mode remains available, not an automatic fallback. This change
was not newly validated on Linux/macOS or with bitmap stipple.
