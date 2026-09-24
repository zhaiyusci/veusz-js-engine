# Comparison with the upstream Web UI

Compared the actual `index.html` controls and `app.js` option mapping at pinned
MolecularRenaissance revision `b351c7b22085ab9c107e4f526c86fc673d3702a6`:

- [Web controls](https://github.com/zhaiyusci/MolecularRenaissance/blob/b351c7b22085ab9c107e4f526c86fc673d3702a6/index.html)
- [Web option mapping and enable/disable logic](https://github.com/zhaiyusci/MolecularRenaissance/blob/b351c7b22085ab9c107e4f526c86fc673d3702a6/app.js)

This is a control/API comparison, not a claim that the widget reproduces every
Web UI feature or all of its defaults. The Veusz integration remains fast-only.

## Changes made in this pass

| Control | Upstream Web UI | Veusz widget |
|---|---|---|
| Element labels | Master switch, initially off | `labels`, initially off |
| Hydrogen labels | Separate `labelHydrogens`, initially on | Added **Formatting -> Labels -> Hydrogen labels**, initially on |
| Atom radius scale | Initial/reset value 1.0 | Default **0.75**, explicitly requested by the user |

Turning off H labels hides only their symbols: atoms, bonds and coordinates are
unchanged. Invisible H labels are not sent to the font-measurement protocol.
With only H atoms and H labels disabled, no label measurements or label padding
are needed. The master label switch still controls all element labels.

Radius scale multiplies each element's covalent radius; it is not a universal
radius in angstroms. Explicitly saved values (including 1.0) remain effective;
settings omitted from a document use the current default.

## Existing mappings

- Scale, atom radius multiplier and orientation; the Web rotation gizmo is
  represented by native numeric pitch/yaw/roll controls.
- Directional light azimuth/elevation.
- Shading mode, including `none` for the Web's shading-enabled switch;
  `textureScale` and `elementTextures`.
- `colored` maps to upstream `colorWash`, `palette` to `colorScheme`.
- Label size is exposed in points and converted to upstream SVG units. Font and
  label color use native Veusz controls and Qt glyph outlines.
- Browser XYZ upload is replaced by embedded multiline XYZ stored in `.vsz`.
  Captions and final document export are handled by native Veusz widgets/export.

## Other Web controls not yet exposed

These are **available in upstream fast mode**; their absence from this widget
is an adapter/UI omission, not a renderer restriction:

| Area | Controls not yet exposed |
|---|---|
| Outlines/shading | `outlineWidth`, `shadingBrightness`, `shadingContrast` |
| Hatch-specific | `variableWidth`, `crossHatch` |
| Color wash | `washStrength`, `colorSaturation` |
| Element patterns | `elementTextureScale` |
| Label styling | `labelBold`, `labelItalic`, `labelStrokeWidth`, `labelStrokeColor`, `labelMatchFill` |
| Additional palettes | `greenCarbon`, `cyanCarbon`, `magentaCarbon` |

The Web enables hatch switches only when shading is on and the style is hatch;
wash settings depend on color wash, pattern size on element textures, label
settings on the master label switch, and label stroke color additionally on
`labelMatchFill` being off. These dependencies should be retained when adding
those controls, rather than merely exposing unused settings.

Current Veusz label styling is deliberately not identical to the Web defaults:
the Web uses italic labels and `labelMatchFill=true`, with a Georgia/Times serif
font. This adapter currently uses the widget's native font (default Arial),
nonitalic labels and a white halo. Future bold/italic support must update the
Qt measurement request as well as renderer options; changing SVG font attributes
alone does not change already outlined glyphs.

## Intentionally outside the fast-only scope

Point lights, cast shadows, point-light distance/attenuation and shadow strength
are not exposed. In Web fast mode the first two are forced off and the dependent
controls disabled. This restriction remains unchanged.

Low-level options available only in the renderer API (for example individual dot
parameters) are not counted as missing Web UI controls here.
