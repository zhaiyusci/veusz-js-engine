# Comparison with the upstream Web UI

Compared the actual `index.html`, `app.js`, `src/types.ts` and `RENDERER.md` at
MolecularRenaissance revision `7b93c9b857a63e2610abe459cca49ba0a9190773`:

- [Web controls](https://github.com/zhaiyusci/MolecularRenaissance/blob/7b93c9b857a63e2610abe459cca49ba0a9190773/index.html)
- [Web option mapping](https://github.com/zhaiyusci/MolecularRenaissance/blob/7b93c9b857a63e2610abe459cca49ba0a9190773/app.js)
- [Renderer contract](https://github.com/zhaiyusci/MolecularRenaissance/blob/7b93c9b857a63e2610abe459cca49ba0a9190773/RENDERER.md)

This is a control/API comparison, not a claim that every Web feature or default
is reproduced. Veusz now defaults to **precise** rendering, with **fast** retained
as an explicit alternative. Directional cast shadows are optional and initially
off (the renderer API default); the Web GUI initially enables them in precise mode.

## This synchronization

| Control / option | Upstream Web UI | Veusz adapter 0.3.1 |
|---|---|---|
| Geometry | Precise by default, optional fast coverage | View -> Render mode, precise by default |
| Cast shadows | Precise supports them, fast forces them off | Lighting -> Cast shadows, initially off; fast ignores but retains saved values |
| Shadow strength | 0..1 | Lighting -> Shadow strength, default 0.8 |
| Quantized shading | Explicitly enabled in precise and fast UI modes | Explicit `quantizeShading: true` |
| Shading levels | 4/8/16/32/64; default 16 | Appearance -> Shading levels; stored as a string, passed as a number |
| Brightness | UI percentage converted to -1..1, default 0 | Appearance -> Shading brightness; -1..1, default 0 |
| Contrast | 0.5..2.5, default 1.2 | Appearance -> Shading contrast; same range/default |
| Stipple delivery | Fixed `bitmap`, shared baked PNG tiles | Explicit `bitmap`, using the same embedded tiles; no per-dot vector expansion |
| Atom radius scale | Default/reset 0.75 | Existing default 0.75 retained |
| Point-light options | Removed from renderer API | Removed obsolete `lightType` argument; only direction angles sent |

The same shading level controls all three textures. N denotes N positive ink
levels plus unpainted paper, not N including white. With shading `none`, no
shading ink is drawn; the chosen levels/brightness/contrast remain saved for later.
The native widget does not reproduce every Web control's dynamic disabled state.

The adapter preserves upstream's tone-band difference geometry and fast template
reuse. It does not replace the new lighting function with an old approximation.
Actual Qt pixel tests, rather than parser validity alone, determine whether
masks/patterns render correctly. No pattern-flattening pass was added speculatively.

## Existing mappings retained

- Scale, atom radius multiplier and orientation; the Web rotation gizmo is
  represented by native numeric pitch/yaw/roll controls.
- Directional light azimuth/elevation.
- Shading style, including `none` for the Web shading-enabled switch;
  `textureScale` and `elementTextures`.
- `colored` maps to upstream `colorWash`, `palette` to `colorScheme`.
- `labels` is initially off, `labelHydrogens` initially on. H-label visibility
  affects only text, not hydrogen atoms or bonds; invisible H labels do not incur
  glyph measurement or padding.
- Label size is in points and converted to upstream SVG units. Font/color use
  native Veusz controls and Qt glyph outlines at upstream paint-layer positions.
- Browser XYZ upload is replaced by embedded multiline XYZ stored in `.vsz`.
  Captions and final document export use native Veusz widgets/export.

All settings retain **flat native storage paths**. Formatting tabs are UI proxies,
not new settings groups. Existing `molecule/scale`, `molecule/font`, etc. remain
valid; new fields are `molecule/shadingLevels`, `molecule/shadingBrightness`,
`molecule/shadingContrast`, `molecule/renderMode`, `molecule/castShadows` and
`molecule/shadowStrength`, not paths under `Appearance/`, `View/` or `Lighting/`.
Documents without a saved render mode now use precise.

## Intentional default/output differences

- Web default scale is 60 SVG units/angstrom (45 pt/angstrom); the widget retains
  18 pt/angstrom. Geometry is not automatically fitted to a canvas.
- Web label size is 17 SVG units (12.75 pt); the widget retains 12 pt and its native
  font (default Arial), nonitalic glyphs and white halo. The Web uses serif/italic
  labels and fill-matched halos. Future bold/italic controls must also change Qt
  measurement requests, not merely upstream SVG text attributes.
- Explicit saved radius values remain effective. The default stays 0.75.
- Quantized shading and corrected lighting intentionally change the appearance
  of documents that previously used the old fast continuous renderer.
- Stipple now uses the upstream bitmap-tile delivery, not forced circle marks.
  This is bitmap texture within SVG geometry, not a screenshot of the whole
  molecule. No browser/Qt pixel-identity claim is made; native Qt export may
  additionally rasterize mask layers or pattern tiles.

## Other fast-compatible Web controls not yet exposed

| Area | Remaining controls |
|---|---|
| Outlines | `outlineWidth` |
| Hatch-specific | `variableWidth`, `crossHatch` |
| Color wash | `washStrength`, `colorSaturation` |
| Element patterns | `elementTextureScale` |
| Label styling | `labelBold`, `labelItalic`, `labelStrokeWidth`, `labelStrokeColor`, `labelMatchFill` |
| Additional palettes | `greenCarbon`, `cyanCarbon`, `magentaCarbon` |

These omissions are adapter/UI scope, not renderer limitations. Web controls have
style-dependent enable/disable rules; future native mappings should account for
those semantics. `labelMatchFill` concerns the halo, not element-colored text.

Point-light type/distance/attenuation are removed from upstream itself; sending
those obsolete keys is an error, not a way to select defaults.

Unlike the upstream white page, Veusz needs a transparent canvas with opaque
molecule bodies. For this pin the adapter internally sets upstream `labels: true`
in precise mode to obtain certified surface-owner layers, then strips text when
user labels are off. This does not turn user labels on or request Qt font metrics.
If certified surface fills cannot be obtained, it reports a nonfatal error and
suggests explicit fast mode instead of emitting transparent white atoms/bonds.
