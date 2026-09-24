# 3D molecule widget — MolecularRenaissance

An independent Veusz **`molecule3d`** widget backed by the author's
[MolecularRenaissance](https://github.com/zhaiyusci/MolecularRenaissance)
renderer. It produces SVG offline in the platform's **browser Worker backend**
(default), or the explicit **QuickJS fallback**. The renderer itself needs no DOM,
WebGL, Node.js, external service or runtime download. Keep the platform browser
backend files alongside the plugin when using the default backend.

## Use

1. Install `veusz_js_engine.py` as the single Veusz plugin. Keep this directory
   under `features/`, including all five renderer modules.
2. Enable **molecule3d** under **Tools -> JS Engine Features...**, then restart
   if it was disabled. Enable it before opening documents containing its type.
3. Select a page or graph and choose **Insert -> 3D molecule**.
4. Choose **water**, **ethanol**, **c60**, or **xyz**. For xyz, paste a complete
   single-frame XYZ document into the XYZ property (its string editor can edit
   multiline text). Coordinates are in angstroms; they are saved in the `.vsz`.
5. Set the physical scale, orientation, shading and element colors. Move/rotate
   with native selection controls; ordinary undo/redo and document export work.

Open [examples/molecules.vsz](examples/molecules.vsz) after enabling the plugin
for examples of all shading styles, labels and inline XYZ.

## Native Properties and Formatting pages

The widget uses Veusz's own Properties and Formatting docks and native tabbed
settings controls, not a custom dialog or a single long properties list.

- **Properties**: Model, XYZ coordinates and native placement/coordinate settings.
- **Formatting -> View**: render mode (default **precise**), scale, atom radius
  scale, pitch, yaw and roll.
- **Formatting -> Appearance**: shading, shading levels, brightness, contrast,
  element colors, palette, texture scale and element patterns.
- **Formatting -> Lighting**: light azimuth/elevation, cast shadows (default off)
  and shadow strength (default 0.8). Shadows apply only in precise mode.
- **Formatting -> Labels**: element labels, hydrogen labels, label size, font and label color.
  Disable **Hydrogen labels** to hide only H symbols while retaining H atoms and bonds;
  this switch defaults to on, matching the upstream Web UI.

Pages use the native icon tabs, with their names in tooltips and page headings.
Native main/visibility controls remain as provided by Veusz. Changes, resets and
multi-selection edits use the normal document operations and undo/redo.

**Formatting pages are presentation, not storage groups.** Saved settings retain their original flat paths:
`Set('molecule/scale', 18)`, `Set('molecule/labels', True)` and
`Set('molecule/font', 'Arial')` remain valid. There are no new `View/scale` or
`Labels/font` storage paths, so existing documents and scripts need no migration.
Restart Veusz after updating the plugin to rebuild the settings interface.

## Size, view and appearance

- `scale`: **points per angstrom**, default 18. Geometry does not auto-fit to
  page size or a user-drawn box. There is no width/height/font-size handle for
  the whole molecule. Natural selection bounds follow the projected geometry.
- `pitch`, `yaw`, `roll`: degrees, composed with upstream's XYZ Euler-to-
  quaternion function. The rotation pivot is the atom-position centroid.
  Veusz's native `rotate` remains a separate 2D rotation of the entire widget.
- `atomRadiusScale`: multiplies upstream covalent sphere radii, not bond radius.
  Default **0.75** (a multiplier, not a uniform 0.75-angstrom radius). Explicitly
  saved values remain unchanged; omitted values use the current default.
- `shading`: hatch (default), stipple, halftone, or none. `textureScale` adjusts
  mark size/spacing. `elementTextures` adds element-identifying textures.
- `shadingLevels`: **4, 8, 16 (default), 32 or 64**, stored as a choice string
  (for example `Set('molecule/shadingLevels', '32')`). The adapter passes a number
  to upstream. Each is the number of positive ink levels, plus unpainted white.
  Quantization is shared by hatch, stipple and halftone, and is inactive for `none`.
- `shadingBrightness`: -1 to 1, default 0; positive values brighten the texture.
  `shadingContrast`: 0.5 to 2.5, default 1.2. Both are applied by upstream after
  directional illumination and before quantization, not reimplemented here.
- `colored` and `palette`: element color wash, independent of shading.
- `lightAzimuth`, `lightElevation`: direction of the parallel light, in degrees.
- `labels`, `labelHydrogens`, `labelSize`: master label switch, H-label switch,
  and label size in points. H-label visibility does not remove hydrogen geometry.
  An all-hydrogen model with H labels off needs no glyph measurements. The widget's
  **Font** and **Color** apply to labels, not to molecule scale or element colors.
  Qt supplies glyph outlines; these replace text at the original paint-layer
  positions, preserving label occlusion. White outlines precede colored glyphs.

The canvas is transparent; atom/bond surface fills remain opaque for occlusion.
For this pinned upstream API the adapter internally requests label-enabled owner
layers in precise mode, even when labels are off, then strips unused text before
Qt processing. This is needed because unlayered monochrome dots/halftone otherwise
rely on the white page rectangle for their white atom/bond interiors. Hidden labels
still cause no Qt glyph measurements. If certified surface fills are unavailable,
the widget reports a nonfatal error suggesting fast mode rather than silently
emitting hollow/transparent atoms or substituting approximate geometry.
Qt SVG ignores `clipPath`, even in Qt 6.11. The adapter translates upstream
clipping to white SVG masks. Point stipple uses upstream's shared embedded PNG
tiles, not an independent SVG circle for every dot. The zero-length-segment to
circle compatibility conversion remains only for upstream mark fallbacks.
A sufficiently capable Qt SVG build with mask/pattern/image support is required;
this integration is tested with Qt 6.11.
**The source SVG combines vector geometry with bitmap stipple textures.** It is
not a screenshot of the whole molecule, but it is not entirely vector either.
Native Qt/Veusz SVG export may additionally rasterize mask layers or pattern tiles,
including hatch. Do not equate an SVG file extension with all-vector contents.

See [the Web UI comparison](WEB_UI_PARITY.md) for the verified control mapping,
intentional default differences, and remaining fast-compatible controls not yet
exposed by this adapter.

## Normal rendering by default; fast remains optional

Adapter **0.3.0** defaults `renderMode` to **`precise`**. This uses upstream's
visible surface boundaries and occlusion rather than depth-sorted full atom
circles. `fast` remains available in Formatting -> View for approximate overlap
and shared templates. Both use `quality: 'export'` for preview and document export;
mode selection is not a switch between low- and high-quality path fitting.

```js
{
  renderMode: props.renderMode, quality: 'export',
  castShadows: props.renderMode === 'precise' && props.castShadows,
  shadowStrength: props.shadowStrength,
  quantizeShading: true, shadingLevels: Number(props.shadingLevels),
  stippleFill: 'bitmap'
}
```

`castShadows` starts **off**, matching the renderer API default, and can be enabled
under Lighting. `shadowStrength` is the fraction of direct light removed by an
occluder, from 0 to 1. Fast mode suppresses shadows without overwriting the saved
switch or strength; switching back to precise restores their effect. Shading
`none` also produces no shadow texture. There is no point-light option.

Existing documents that omit `renderMode` now use precise rendering. Set
`Set('molecule/renderMode', 'fast')` to retain approximate geometry. New fields
are flat root settings, including `molecule/castShadows` and
`molecule/shadowStrength`; old scale, rotation and font paths remain unchanged.
Mode and shadow values participate in the render cache.

Precise labels respect visibility: labels on fully occluded atoms can disappear,
where fast-mode labels may still be emitted and overpainted. The adapter does
not invent visible regions or force hidden labels to the front. Upstream's safe
continuous-hatch fallback remains possible; missing certified surface fills,
however, are rejected as described above to preserve transparent-output semantics.

This remains an engraving renderer, not photorealistic rendering or ORTEP thermal
ellipsoids; sphere radii are not atomic displacement parameters. Precise scenes
can have more paths/masks and cost more in Qt painting/export even when browser
JS generation is quick. See [precise-mode validation](PRECISE-VALIDATION.md) for
measured scope and limitations.

## Upstream synchronization: `7b93c9b` / adapter 0.2.0

The five unmodified classic scripts are pinned at `7b93c9b857a63e2610abe459cca49ba0a9190773`.
This brings shared quantized shading, reusable fast atom templates, corrected
lighting/art ordering, and the halftone fix that paints mutually exclusive tone
bands instead of stacking full patterns over cumulative regions.

Existing documents retain their setting paths, scale, radius multiplier and label
font semantics, but their shading can intentionally look different: this update
uses the new quantized renderer, not a promise of old-pixel reproduction.

The upstream GUI uses shared bitmap stipple tiles. Adapter **0.3.1** restores
**`stippleFill: 'bitmap'`**, matching that design. Earlier adapters incorrectly
forced vector marks, then expanded each mark to a circle for Qt. With C60,
`textureScale=0.2` and shadows enabled, this bypassed the intended optimization
and exceeded the SVG output budget. The fix reuses upstream's embedded PNG tiles;
it does not raise the output limit or silently increase the user's texture scale.
See [bitmap stipple validation](BITMAP-VALIDATION.md).

The removed `lightType`, `lightDistance` and `lightAttenuation` options must not be
sent even with historical directional/default values; upstream now rejects them.
The 0.2.0 synchronization initially kept the fast-only restriction; adapter 0.3.0
subsequently enabled precise geometry and optional directional cast shadows as
described above. No point-light controls are reintroduced.

### Historical renderer cost (before this synchronization)

**All timings below describe the previous renderer, not `7b93c9b` or the browser
backend's current performance.** They are retained only as historical context.

Previous widget measurements at **18 pt/angstrom**, hatch, labels off, fresh process
per case (including deferred JS loads, but excluding platform installation and Qt
painting/export):

| Model | Radius multiplier 0.75, first reply | Radius multiplier 1.0, first reply |
|---|---:|---:|
| Water | 0.187 s | 0.241 s |
| Ethanol | 0.406 s | 0.421 s |
| C60 | **2.106 s** | 0.184 s |

C60 at 0.75 exposes many more visible bonds; its SVG is about 361 KB rather than
79 KB at 1.0. Cached replies take about 2 ms at 0.75, but changing orientation
requires a new render. These are local measurements, not latency guarantees.

Historical baseline with **atom radius multiplier 1.0**, before the widget default
changed to 0.75: actual bundled QuickJS, pinned upstream,
`fast + export + hatch + colorWash`, 640x480 SVG canvas. Two renders per case, timed inside JavaScript; **not** a
browser measurement and **not** total Veusz/Qt export latency:

| Model | Scale (SVG units/angstrom) | First / second render |
|---|---:|---:|
| Water | 24 (18 pt/angstrom) | 213 / 211 ms |
| Ethanol | 24 | 383 / 384 ms |
| C60 | 24 | 155 / 150 ms |
| C60 | 60 (45 pt/angstrom) | 463 / 464 ms |

C60 at scale 24: stipple 416/405 ms; halftone 267/264 ms. SVG transmission was
under 4 ms per case. Complexity is geometry/style dependent, not monotonic in
atom count: at multiplier 1.0 this C60 model reuses atom templates and needs no
sampled visible bond masks. Multiplier 0.75 exposes more bonds, so it costs more
to render and the old C60 timing does not describe the new default. Larger or unusually overlapping XYZ models can be slower. These
are local measurements, not an interactive latency guarantee. Completed widget
renders are cached; changing a view or style requires fresh rendering.

For the checked-in six-widget sheet with the **0.75 default** (mixed styles,
including C60 halftone), an actual 144-dpi Veusz PNG export took about **6.20 s**.
Its subsequent native SVG export took **12.80 s**, despite cached JS replies:
Qt/Veusz mask/pattern processing and serialization are separate costs. Fast mode
solves the earlier JS geometry bottleneck, not every native export bottleneck.

## XYZ scope and limits

Example:

```text
3
Water, angstroms
O  0.000  0.000  0.000
H  0.957  0.000  0.000
H -0.240  0.927  0.000
```

XYZ uses the atom count, one comment line, then exactly `element x y z` per atom.
Single-frame decimal/exponent coordinates are accepted; malformed counts,
unknown elements, nonfinite coordinates, extra columns and multiple frames fail
visibly. Empty XYZ leaves an empty widget and does not load the renderer.

The adapter limits input to 65,536 characters, 96 atoms, 256 inferred bonds and
2048 SVG units per natural canvas dimension. These are bounded first-version
limits, not limits of the upstream parser. Errors are local to the widget;
correcting its input recovers without restarting Veusz.

Bonds are inferred geometrically using upstream covalent radii and distance
cutoffs. XYZ carries no bond order, and this adapter neither validates molecular
chemistry nor computes conformers. Built-in models are idealized examples, not
experimental structures or optimized coordinates. For **2D SMILES**, use the
separate [SMILES widget](../smiles/README.md), which remains unchanged.

## Provenance and tests

The upstream runtime files are unmodified and checksum-pinned; see
[UPSTREAM.md](UPSTREAM.md). The upstream project does not declare a public
license in the pinned revision; integration was authorized by its author.
That authorization is not a fabricated MIT/Apache license for upstream code.

```text
python features/molecule3d/tools/vendor_renderer.py --check
python features/molecule3d/test/test_molecule3d_feature.py
python features/molecule3d/test/test_molecule3d_formatting.py
```

Tests use real Qt against the sibling `../upstream-veusz` checkout, without
modifying host sources or saved preferences. They follow `VEUSZ_JS_ENGINE_BACKEND`
(default browser); set it to `quickjs` to exercise the explicit fallback. Browser
selection follows `VEUSZ_JS_ENGINE_BROWSER`. Run these suites sequentially because
they share export fixture paths. The standalone tests require user-site PyQt;
`python -S` is appropriate for the stdlib-only integrity checker, not these Qt tests.

Regressions cover all five shading levels across all three styles, numeric
renderer options, invalid-input recovery, cache isolation, actual Qt ink inside
atom silhouettes, precise visibility/opaque white bodies, shadows, label geometry,
native controls/undo, old examples and `.vsz` root-setting save/load. See
[BITMAP-VALIDATION.md](BITMAP-VALIDATION.md) for current bitmap/dense-C60 results,
[PRECISE-VALIDATION.md](PRECISE-VALIDATION.md) for the initial precise-mode work,
and [UPGRADE-VALIDATION.md](UPGRADE-VALIDATION.md) for the preceding vendor upgrade.
