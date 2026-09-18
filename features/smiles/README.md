# SMILES molecular structures

Draw a **two-dimensional molecular structure** directly in a Veusz text label.
Powered by **SmilesDrawer 2.4.1**, running offline in the platform's QuickJS
engine. No browser, WebGL, Node.js, remote service or extra binary is needed.

## Use

1. Install `veusz_js_engine.py` in Veusz's plugin preferences and restart.
2. Ensure **smiles** is enabled in **Tools -> JS Engine Features...**. Global
   enablement changes take effect after restarting Veusz.
3. Add a label and enter a SMILES string, for example `CCO`.
4. In the label's **Text** settings, check **SMILES**.

The existing label remains a normal Veusz object: move, align, rotate and save it
as usual. The SMILES string and display settings stay in the `.vsz` document.
Enable only one renderer (SMILES, MathJax or KaTeX) on a given text element;
otherwise the first enabled renderer in feature discovery order claims it.

| Setting | Default | Meaning |
|---|---|---|
| `Text/smiles` | `False` | Interpret the label text as SMILES rather than ordinary text |
| `Text/smilesColored` | `True` | Element colors; off uses the label's text color |
| `Text/smilesScale` | `1` | Overall structure scale, from 0.1 to 10 |
| Existing Text font/size | label's values | Atom label font and base diagram size |

Settings are registered at startup, but `headless.js` and `smiles-drawer.js` are
**loaded once on the first enabled, nonempty drawing**. Ordinary labels and empty
SMILES labels do not load them. Completed drawings are cached by source, size,
scale, color mode, text color and font identity (up to 128 entries per runtime).
Globally disabling the feature prevents even its entry point from running.

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
plugin to see six examples on one page. No external molecule files are needed.

## Rendering and limits

- Rings, double/triple bonds, solid/hashed stereobonds, isotopes, charges and
  hydrogen subscripts are produced by SmilesDrawer's parser/layout.
- Atom labels are measured and outlined by Qt in the label's font using the
  platform's existing two-pass measurement protocol. Final drawings contain
  **vector geometry, not browser text or bitmap screenshots**.
- Backgrounds are transparent. Upstream label masks are subtracted from bond
  geometry, avoiding opaque rectangles and relying on neither CSS transforms
  nor SVG mask support in the target Qt version. Circular wedge cuts use a
  fine polygon approximation.
- Size follows the label font size; Structure scale then enlarges/shrinks the
  entire diagram. The base upstream 11 pt label corresponds to 14.6667 SVG
  CSS-pixel units. Diagram depth is zero (bottom baseline); normal Veusz
  alignment positions the whole box.
- Malformed syntax, unmatched/self ring closures, missing font outlines and
  drawing failures are displayed as errors, rather than silently hiding labels.
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

- `feature.js`: feature settings, lazy-load handshake, cache and size conversion.
- `headless.js`: feature-local SVG element builder and metric-only canvas shim,
  label outlining and portable bond clipping. Not a general DOM implementation.
- `smiles-drawer.js`: **unmodified** `dist/smiles-drawer.min.js` from the official
  npm package `smiles-drawer@2.4.1`; includes `chroma-js@2.4.2`.
- `LICENSE-SMILESDRAWER.txt`: upstream MIT license.
- `LICENSE-CHROMA.txt`: bundled chroma-js BSD-3-Clause and ColorBrewer notice.

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
platform's QuickJS library. They exercise real cold/warm rendering, atom glyph
outlines, stereo/isotope/charge examples, transparent SVGs, input limits, scale,
font/color cache separation, real PNG/SVG export, and `.vsz` save/load settings.
Outputs are in the workspace's ignored `build-test-smiles/` directory. Tests do
not save feature preferences to the user's settings database.
