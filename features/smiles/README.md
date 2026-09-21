# SMILES molecule widget

Draw a **two-dimensional molecular structure** as an independent Veusz widget.
It is not a text renderer and adds nothing to labels' or axes' Text settings.
Powered by **SmilesDrawer 2.4.1**, running offline in the platform's QuickJS
engine. No browser, WebGL, Node.js, remote service or extra binary is needed.

## Use

1. Install `veusz_js_engine.py` in Veusz's plugin preferences and restart.
2. Ensure **smiles** is enabled in **Tools -> JS Engine Features...**. Global
   enablement changes take effect after restarting Veusz.
3. Select a page or graph and choose **Insert -> SMILES molecule**.
4. Enter a SMILES string, for example `CCO`, in the widget's **SMILES** property.
5. Set its own **Font size**, for example `12pt` or `18pt`, to size the structure.
   Move or rotate the widget with the selection controls, or edit its position
   and rotation properties.

The document tree contains a real `smiles` object, separate from ordinary labels.
Its structure and display settings are saved in `.vsz`; insertion and native
geometry changes participate in Veusz undo/redo. A caption, if needed, is a
separate ordinary label and may independently use MathJax or KaTeX.

| Widget setting | Meaning |
|---|---|
| `smiles` | Molecular structure string; default `CCO` |
| `colored` | Element colors, enabled by default; off uses the widget's `color` |
| `xPos`, `yPos` | Native Veusz position lists; default center of the container |
| `size` | Widget-local font size, default `12pt`; controls the whole structure |
| `rotate` | Native Veusz rotation angles in degrees |
| `hide` | Hide the widget without rendering it |
| `positioning`, `xAxis`, `yAxis` | Native relative or graph-axis positioning |
| `font` | Widget-local atom-label font family (formatting); default Arial |
| `color` | Widget-local monochrome drawing color (formatting); default black |

The drawing has a **natural size determined by its own font size**. Changing
`12pt` to `24pt` doubles both the atom labels and bond geometry. Molecules at the
same font size share the same nominal atom-label and bond scale, rather than
being squeezed into identical boxes. Page size does not change that physical
scale; export DPI changes only the number of pixels used to represent it.

The selection box follows the rendered structure and has move/rotation controls,
not resize handles. There are no `width` or `height` properties. Rotation is
around the structure center. Native position/rotation settings accept lists or
datasets; none of this adds settings to ordinary text labels.

For a document script:

```python
Add('page', name='page1', autoadd=False)
To('page1')
Add('smiles', name='molecule1', autoadd=False)
Set('molecule1/smiles', 'N[C@@H](C)C(=O)O')
Set('molecule1/xPos', [0.5])
Set('molecule1/yPos', [0.5])
Set('molecule1/size', '14pt')
```

### Previous text-label prototype

The previous `Text/smiles`, `Text/smilesColored` and `Text/smilesScale` settings
are removed, not kept as hidden text switches. Old prototype documents are not
automatically migrated: replace molecular `label` objects with `smiles` objects,
move the source from `label` to `smiles`, and preserve positions.
`Text/smilesColored` becomes `colored`, `Text/font` becomes `font`, and
`Text/size` becomes the widget's own `size`. If the prototype used a non-default
`Text/smilesScale`, multiply its font size by that scale. Remove the old Text
settings; the widget is positioned by its center instead of label alignment.

For the intermediate box-sized widget prototype, remove `width`/`height` and
set `size` in points instead. There is no automatic conversion from its fitted
box to a font size. The bundled example uses font sizes already.

## Lazy loading

The widget type and its properties are registered at startup, but `headless.js`
and `smiles-drawer.js` are **loaded once on the first visible, nonempty drawing**.
Creating a widget, hiding it, or leaving its source empty does not load them.
Completed drawings are cached by source, font size, color mode, drawing color
and font identity (up to 128 entries per runtime). Moving/rotating a widget
reuses the same geometry. Globally disabling the feature prevents even its entry point
from running: its widget type and Insert action are then unavailable. Enable
it and restart before opening documents which contain `smiles` widgets.

## Examples

| Molecule | SMILES |
|---|---|
| Ethanol | `CCO` |
| Benzene | `c1ccccc1` |
| Aspirin | `CC(=O)Oc1ccccc1C(=O)O` |
| Caffeine | `Cn1c(=O)c2c(ncn2C)n(C)c1=O` |
| Alanine with stereochemistry | `N[C@@H](C)C(=O)O` |
| Isotope and charge | `[13CH3][NH3+]` |
| Separate ionic fragments | `[Na+].[Cl-]` |

Open **[examples/molecules.vsz](examples/molecules.vsz)** after enabling the
plugin to see six independent molecule widgets with normal label captions.
No external molecule files are needed.

## Rendering and limits

- Rings, double/triple bonds, solid/hashed stereobonds, isotopes, charges and
  hydrogen subscripts are produced by SmilesDrawer's parser/layout.
- Atom labels are measured and outlined by Qt in the widget's font using the
  platform's measurement protocol. Final drawings contain **vector geometry,
  not browser text or bitmap screenshots**.
- Backgrounds are transparent. Upstream label masks are subtracted from bond
  geometry, avoiding opaque rectangles and relying on neither CSS transforms
  nor SVG mask support in the target Qt version. Circular wedge cuts use a
  fine polygon approximation.
- Malformed syntax, unmatched/self ring closures, missing font outlines and
  drawing failures are shown inside the widget; other objects keep drawing.
- Up to **4096 input characters and 256 parsed atoms** per structure. These are
  interactive drawing limits, not a substitute for chemistry validation.
- This is a depiction tool, **not a chemical valence/aromaticity validator**, a
  structure editor, a name-to-structure service, or a 3D/conformer generator.
  Use supported SMILES and check scientific content as with any depiction tool.
- Ordinary outline-capable fonts (e.g. Arial, DejaVu Sans) are recommended.
  Raster-only fonts cannot supply vector atom labels and produce a clear error.
- Compact pseudo-label abbreviation is disabled so atom labels can be handled
  explicitly. Rendering/layout can differ from another chemical drawing tool.

## Files and provenance

- `feature.js`: widget declaration, properties, lazy-load handshake and cache.
- `headless.js`: feature-local SVG element builder and metric-only canvas shim,
  label outlining and portable bond clipping. Not a general DOM implementation.
- `smiles-drawer.js`: **unmodified** `dist/smiles-drawer.min.js` from the official
  npm package `smiles-drawer@2.4.1`; includes `chroma-js@2.4.2`.
- `LICENSE-SMILESDRAWER.txt`: upstream MIT license.
- `LICENSE-CHROMA.txt`: bundled chroma-js BSD-3-Clause and ColorBrewer notice.

The Python platform supplies the generic `target: 'widget'` integration. There
is no SMILES-specific Python widget or molecular drawing code in the platform.

Bundle SHA-256:
`6b0397cd52a708eeafb995f191d6d972449377e5603ae603cb210f537666fddc`

Reproduce the vendor files without executing npm lifecycle scripts:

```text
python features/smiles/tools/vendor_smiles.py
# Or use an already downloaded official tarball:
python features/smiles/tools/vendor_smiles.py --archive path/to/smiles-drawer-2.4.1.tgz
```

The helper checks the pinned archive SHA-512 and bundle SHA-256 before writing.
The wrapper, adapter and test/tool sources are Apache-2.0 (this project).

Upstream: https://github.com/reymond-group/smilesDrawer

SmilesDrawer paper: https://doi.org/10.1021/acs.jcim.7b00425

## Tests

```text
python features/smiles/test/test_smiles_feature.py
```

Tests explicitly use the sibling `upstream-veusz` checkout with PyQt6 and the
platform's QuickJS library. They exercise real widget creation, absence of Text
injection, cold/warm rendering, atom glyph outlines, stereo/isotope/charge
examples, natural selection bounds, movement/rotation controls, font-size and
DPI scaling, page-size independence, font/color cache separation, actual PNG/SVG
export, and `.vsz` save/load. Outputs are in the workspace's ignored
`build-test-smiles/` directory. Tests do not save feature preferences to the
user's settings database.
