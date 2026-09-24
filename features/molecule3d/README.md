# 3D molecule widget — MolecularRenaissance, fast mode

An independent Veusz **`molecule3d`** widget backed by the author's
[MolecularRenaissance](https://github.com/zhaiyusci/MolecularRenaissance)
renderer. It runs offline in the existing QuickJS engine and produces SVG:
no browser, WebGL, Node.js, service or runtime download is required.

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
- **Formatting -> View**: scale, atom radius scale, pitch, yaw and roll.
- **Formatting -> Appearance**: shading, element colors, palette, texture scale
  and element patterns.
- **Formatting -> Lighting**: light azimuth and elevation.
- **Formatting -> Labels**: element labels, hydrogen labels, label size, font and label color.
  Disable **Hydrogen labels** to hide only H symbols while retaining H atoms and bonds;
  this switch defaults to on, matching the upstream Web UI.

Pages use the native icon tabs, with their names in tooltips and page headings.
Native main/visibility controls remain as provided by Veusz. Changes, resets and
multi-selection edits use the normal document operations and undo/redo.

**Only presentation changed.** Saved settings retain their original flat paths:
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
- `colored` and `palette`: element color wash, independent of shading.
- `lightAzimuth`, `lightElevation`: direction of the parallel light, in degrees.
- `labels`, `labelHydrogens`, `labelSize`: master label switch, H-label switch,
  and label size in points. H-label visibility does not remove hydrogen geometry.
  An all-hydrogen model with H labels off needs no glyph measurements. The widget's
  **Font** and **Color** apply to labels, not to molecule scale or element colors.
  Qt supplies glyph outlines; these replace text at the original paint-layer
  positions, preserving label occlusion. White outlines precede colored glyphs.

The canvas is transparent; atom/bond surface fills remain opaque for occlusion.
Qt SVG ignores `clipPath`, even in Qt 6.11. The adapter translates upstream
clipping to white SVG masks and expands zero-length stipple segments into circle
marks, rather than trusting parser validity. A sufficiently capable Qt SVG build
with mask/pattern support is required; this integration is tested with Qt 6.11.
**Native Qt/Veusz SVG export may embed rasterized mask layers or pattern tiles**,
even though the feature returns vector SVG markup with no embedded images.
Do not assume the final exported document is entirely vector, including hatch.

See [the Web UI comparison](WEB_UI_PARITY.md) for the verified control mapping,
intentional default differences, and remaining fast-compatible controls not yet
exposed by this adapter.

## Fast mode is the only mode

Every render, **including document export**, explicitly sets:

```js
{renderMode: 'fast', quality: 'export', lightType: 'directional', castShadows: false}
```

There is no precise-mode, point-light or cast-shadow setting. Unrecognized input
properties cannot override these restrictions. `fast` is an upstream geometry
mode, **not** an alias for `quality: 'preview'`; vector output is retained.

Fast rendering uses depth-sorted complete atom circles, shared shading templates
and sampled bond visibility. It does not compute exact sphere/sphere intersection
boundaries or general exact bond/bond occlusion. Some overlaps can look different
from the upstream precise renderer. This is not a photorealistic or ORTEP thermal-
ellipsoid renderer, and sphere radii are not atomic displacement parameters.

### Measured renderer cost

Current widget measurements at **18 pt/angstrom**, hatch, labels off, fresh process
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
```

Tests use real QuickJS and Qt against the sibling `../upstream-veusz` checkout,
without modifying host sources or user preferences.
