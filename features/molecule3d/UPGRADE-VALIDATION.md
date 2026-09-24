# MolecularRenaissance 7b93c9b integration validation

Historical adapter 0.2.0 results. Precise became the default in 0.3.0; 0.3.1
restores upstream bitmap stipple instead of the incorrect forced-marks policy.
See [BITMAP-VALIDATION.md](BITMAP-VALIDATION.md) for current stipple validation.

## Scope

Upgrade from `b351c7b22085ab9c107e4f526c86fc673d3702a6` to
`7b93c9b857a63e2610abe459cca49ba0a9190773`; adapter version 0.2.0.
Five upstream classic scripts remain exact, hash-pinned bytes. Four changed;
`wash.js` is identical. No npm build or lifecycle script ran.

Added native Appearance settings: `shadingLevels` (4/8/16/32/64, default 16),
`shadingBrightness` (default 0), `shadingContrast` (default 1.2). Native storage
paths remain flat. The adapter explicitly enables quantized fast rendering,
requests vector stipple marks and stops sending the removed `lightType` key.
Existing scale, atom radius 0.75, rotations, label/font behavior and fast/no-shadow
scope are retained. New shading appearance is intentional, not pixel compatibility
with the previous renderer.

## Executed checks

Environment: Windows, standalone Python/PyQt against the sibling upstream Veusz
checkout, plus the real installed frozen `C:\Program Files\Veusz\veusz.exe`.
No saved Veusz preferences or upstream Veusz sources were changed.

| Check | Result |
|---|---|
| `python -S features/molecule3d/tools/vendor_renderer.py --check` | All 5 files match size/SHA256 |
| QuickJS `test_molecule3d_feature.py` | 23 passed, final full run 52.968 s |
| QuickJS `test_molecule3d_formatting.py` | 12 passed, 2.303 s |
| Firefox `test_molecule3d_feature.py` | 22 passed before adding the dedicated plateau test, 63.440 s |
| Firefox dedicated plateau regression added afterward | 1 passed, 4.336 s |
| Firefox `test_molecule3d_formatting.py` | 12 passed on full rerun, 19.972 s |
| Frozen Veusz + Firefox | Four-feature SVG/PNG document export passed |
| Frozen Veusz + Edge | Four-feature SVG/PNG document export passed |
| Frozen Veusz + explicit QuickJS | Four-feature SVG/PNG document export passed |
| `git diff --check` | Passed |

The four-feature smoke test covers MathJax, KaTeX, SMILES and molecule3d together.
Its isolated in-process feature setup does not alter saved feature preferences.

Coverage includes all 15 shading-style/level combinations, option types and
ranges, visible errors and recovery, cache switching/restoration, native dropdown
editing/reset/undo, flat-path document save/load, actual Qt ink within atom
silhouettes, label alignment, XYZ validation, C60, and the existing six-widget
example. Native Appearance and example export images were also visually inspected.
No speculative pattern-flattening pass was needed for the tested Qt build.

## Targeted halftone overprint regression

The test adapts upstream's
[`halftone-levels-browser-test.js`](https://github.com/zhaiyusci/MolecularRenaissance/blob/7b93c9b857a63e2610abe459cca49ba0a9190773/halftone-levels-browser-test.js)
fixture to the real Qt renderer **after** the adapter's clip-to-mask conversion.

- Four common coverage plateaus: 0.25, 0.5, 0.75, 1.
- Three texture scales: 0.2, 1, 2.5.
- Five level counts: 4, 8, 16, 32, 64.
- 60 SVG/raster samples; central 32-SVG-unit plateau only, not the full image.
- Nonempty texture required; permitted normalized ink drift remains 0.003.
- Observed maximum cross-level drift: **0.0**, both QuickJS and Firefox.

This verifies level-count overprint invariance, **not** absolute coverage
calibration or browser/Qt raster equivalence. At small mark sizes Qt sampling can
change the measured coverage substantially; this test does not assert that the
measured ink equals the requested coverage. Different level counts may legitimately
change whole-molecule ink outside common plateaus.

## Cross-engine export comparison

The final frozen-Veusz sample PNGs are all 755 x 566. Edge and QuickJS exports are
byte-identical. Firefox differs from them in 50 pixels (94 RGBA channels; maximum
channel difference 35). No claim of complete cross-engine pixel identity is made;
all three pass the functional export checks. This is not a general screenshot
similarity threshold used to relax the geometry regressions.

Output locations (generated, not source-controlled):

- `build-test-browser-veusz/browser-firefox/{results.json,browser-document.png,browser-document.svg}`
- `build-test-browser-veusz/browser-msedge/{results.json,browser-document.png,browser-document.svg}`
- `build-test-browser-veusz/quickjs-firefox/{results.json,browser-document.png,browser-document.svg}`
- `build-test-molecule3d/six-widget-example.png`
- `build/molecule3d-formatting-appearance.png`

## Failures and reruns recorded

- Initial sandbox Firefox launch failed on temporary profile access. The identical
  installed-Veusz command was rerun with approved wider access and passed.
- One Firefox native-formatting case timed out during browser startup, before
  feature code loaded. A complete 12-case formatting rerun passed; the timeout was
  not suppressed or counted as a pass. No startup-timeout code was changed here.
- The first QuickJS suite run loaded an in-progress version of a new invalid-data
  test that patched `get`, while native reading uses the `val` property's bound
  getter. Correcting the fixture to patch `_val`/`_ref` made the isolated case and
  final complete suite pass. Production error checks were not weakened.
- One duplicate QuickJS run was intentionally cancelled to prevent concurrent
  writes to shared export fixtures; it is not counted as a passing run.
- Existing external-Python `_distutils_hack` site warning and optional astropy/SAMP
  notices appeared. They did not fail the final runs. Qt tests need user-site
  PyQt; `-S` is used only for the stdlib integrity checker.

## Reproduction

Run suites sequentially: they share export fixture paths.

```powershell
$env:VEUSZ_JS_ENGINE_BACKEND='quickjs'
python features/molecule3d/test/test_molecule3d_feature.py
python features/molecule3d/test/test_molecule3d_formatting.py

$env:VEUSZ_JS_ENGINE_BACKEND='browser'
$env:VEUSZ_JS_ENGINE_BROWSER='C:\Program Files\Mozilla Firefox\firefox.exe'
python features/molecule3d/test/test_molecule3d_feature.py
python features/molecule3d/test/test_molecule3d_formatting.py

.\test\run_browser_veusz.ps1
.\test\run_browser_veusz.ps1 -Browser 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
.\test\run_browser_veusz.ps1 -Backend quickjs
python -S features/molecule3d/tools/vendor_renderer.py --check
```

This upgrade was not newly exercised on Linux/macOS, in upstream precise mode, or
with upstream bitmap stipple. Qt's native SVG export can still rasterize masks or
pattern tiles even though the adapter requests vector marks. Restart Veusz after
updating; existing running feature contexts are not hot-reloaded.
