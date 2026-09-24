# Restore upstream bitmap stipple — adapter 0.3.1

## Correction

The adapter had explicitly forced `stippleFill: 'marks'` instead of upstream's
bitmap texture design. Its Qt workaround then expanded each zero-length mark
into a separate circle. This was the wrong policy: dense stipple no longer
benefited from the shared bitmap tiles and could exceed the 16 Mi-character
SVG output guard. A previous statement that point count necessarily drives the
user's output size applied to this mistakenly selected marks path, not to the
intended upstream bitmap path.

The fix is `stippleFill: 'bitmap'`, matching upstream. No vendor script was
patched, output/cache budget raised, point density reduced, texture scale
changed, shadow disabled, or whole molecule flattened into a PNG. The source
SVG combines geometry with embedded PNG texture tiles. This is deliberately
not advertised as entirely vector. Native Qt SVG export can also rasterize
masked layers/patterns; a separate UI-only image cache has **not** been added.

The existing circle conversion remains for any upstream mark fallback. The
main precise path and fast atom templates can use upstream bitmap stipple.

## Actual user document

Read-only source: `C:\Users\jairy\Desktop\a.vsz`. Actual molecule settings:

- C60; precise; scale 18 pt/angstrom; atom radius multiplier 0.75;
- stipple; texture scale **0.2**; shading levels 16;
- monochrome; cast shadows **on**, strength 0.8; labels off.

A private installed `C:\Program Files\Veusz\veusz.exe` process loaded a byte-identical
workspace copy and exported the complete document, including its MathJax and
SMILES widgets, to PNG and SVG. The original file's SHA-256 was unchanged:
`f77ebd837eab10ff91842c7d59105306595dcf96d2b6ec779503ae84b5d28aa7`.
Preference writes were disabled in that disposable process.

Environment: Veusz 4.2.1, frozen Python 3.13.12, **Qt 6.10.2**, Firefox browser
backend. The ordinary 30-second browser RPC timeout was retained. Result: passed,
no new platform errors/notes; browser tree closed and temporary profile cleaned.
The first test-launch attempt used a nonexistent `CommandInterface.Load` method;
this test-only mistake was corrected to `document.load` before the passing rerun.

Direct feature output with the same settings:

| Measurement | Result |
|---|---:|
| SVG UTF-8 bytes | 2,036,839 (~1.94 MiB) |
| SVG UTF-16 code units | 2,036,828 |
| Stipple mode metadata | `bitmap` |
| Embedded PNG tile images | 6 |
| Decoded PNG bytes, total | 37,862 |
| Circle elements, total | 60 (not hundreds of thousands of dot nodes) |
| Native Qt raster | 219 x 214 pixels, visibly nonblank |
| Complete document PNG | 708 x 708 pixels |

The complete document PNG was visually inspected. The post-export direct request
was potentially cached; its timing is **not** a cold-render performance result.
Generated proof artifacts are under `build-test-molecule3d-stipple/actual-host/`:
`actual-host-results.json`, `actual-document.png`, `actual-document.svg`,
`actual-c60-bitmap.svg`, `actual-c60-qt.png`, and `input-a.vsz`.
The disposable runner/plugin live one directory above. They are local test
artifacts, not a plugin to install in preferences.

## Regression suites

Full suites against the source Veusz checkout, Python 3.14 / Qt 6.11:

| Backend | Feature tests | Native formatting tests |
|---|---:|---:|
| Firefox | 29 passed (84.733 s) | 13 passed (20.843 s) |
| Explicit QuickJS | 29 passed (60.079 s) | 13 passed (2.063 s) |

Suites ran sequentially. Existing environment `_distutils_hack`, optional astropy,
SAMP and Python deprecation notices were nonfatal. These wall times include
startup, Python pixel checks, native UI and export; they do not compare JS speed.

The new permanent dense-C60 test uses the actual parameter combination without
reading a user's Desktop file. It verifies bitmap metadata, embedded PNGs,
output below the unchanged limit, fewer than 1,000 circle elements, and actual
Qt ink/pixel differences versus no shading. Parser validity alone is insufficient.

SVG validation now permits only embedded, strictly base64-decoded PNG image data
with valid PNG signatures and successful Qt decoding. It still rejects script,
foreign objects, leftover SVG text and external image/resource references.
Existing silhouette/no-leakage, white atom/bond opacity, occlusion, shadows,
quantization, label geometry, cache, native undo and document round-trip tests
remain in place. Halftone's common-coverage plateau drift remains 0.0.

## Scope

This fixes the actual dense-stipple failure and restores upstream's chosen texture
representation. It does not remove all resource limits or promise browser/Qt pixel
identity at arbitrary print resolutions. UI-only whole-widget bitmap caching and
any separate vector-export improvements are distinct work, not hidden changes in
this fix. Restart Veusz to replace the already-loaded adapter runtime.
