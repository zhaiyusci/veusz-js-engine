# MolecularRenaissance provenance

- Repository: https://github.com/zhaiyusci/MolecularRenaissance
- Pinned commit: `7b93c9b857a63e2610abe459cca49ba0a9190773`
- Previous pin: `b351c7b22085ab9c107e4f526c86fc673d3702a6`.
- Upstream package: `molplotter`, version `0.2.0` (`private: true`).
- Source: root-level classic runtime artifacts, downloaded as raw bytes from
  `https://raw.githubusercontent.com/zhaiyusci/MolecularRenaissance/7b93c9b857a63e2610abe459cca49ba0a9190773/<filename>`.
- These five scripts are **unmodified**: no rebuilding, minification, line-ending
  normalization, injected headers, or npm lifecycle scripts.
- Dependency load order: `dot-regions.js`, `boundaries.js`, `wash.js`, `dots.js`,
  `renderer.js`. The renderer exposes `globalThis.MolEngraver` in a classic-script
  runtime, with no DOM or Node required. No additional runtime script is needed:
  the new shared-stipple implementation and PNG tile palettes are bundled into
  `renderer.js`, not downloaded as separate assets.
- Precise mode defaults to `quantizeShading: true`; fast mode retains its historical
  behavior when that option is omitted. The upstream GUI and this adapter explicitly
  enable it in fast mode. `shadingLevels` defaults to 16. Upstream's default
  `stippleFill: 'bitmap'` uses embedded PNG data URLs in SVG image patterns; adapter
  0.3.1 now explicitly selects that same bitmap path. Earlier forced `marks` output
  bypassed upstream's texture optimization and caused dense-stipple size failures.
  The correction is in the adapter only; these vendor files remain unchanged.

## Permission and license status

The user identifies this as their own repository and explicitly authorized its
integration into this workspace as an independent molecule3d feature. The complete
recursive Git tree at the pinned commit (306 entries, `truncated: false`) was
checked via the [official GitHub API](https://api.github.com/repos/zhaiyusci/MolecularRenaissance/git/trees/7b93c9b857a63e2610abe459cca49ba0a9190773?recursive=1):
no path contains LICENSE, LICENCE, COPYING, or NOTICE (case-insensitive). No upstream
LICENSE file was found, and its package metadata specifies no license.
**Upstream license is unspecified.** Author permission for this integration is not
a public license grant: this integration does not invent, reassign, or claim a
license for the upstream artifacts. Preserve upstream notices; clarify redistribution
licensing with the author before independent redistribution.

## Reproduction and integrity

From the workspace root, using any Python 3 interpreter with standard-library
HTTPS support:

```text
python features/molecule3d/tools/vendor_renderer.py
python features/molecule3d/tools/vendor_renderer.py --check
```

The helper pins the repository, commit, version, sizes and SHA256s, downloads only
these five files, rejects byte/hash mismatches before writing any artifact, and
performs no upstream builds. `--check` is offline. Network approval/TLS constraints
of the host environment still apply; the helper does not bypass them. Downloads
for this pin succeeded with standard-library HTTPS and normal certificate
verification in the workspace sandbox; no escalation or TLS bypass was used.

| File | Bytes | SHA256 | Byte change from previous pin |
| --- | ---: | --- | ---: |
| dot-regions.js | 27436 | `31194c110bbf515fe899559c629cb8db4f56c4b4528acb390c4b493f01d771a1` | +339 |
| boundaries.js | 53328 | `dad09e51b6add3abd714aaa127107f2fca310640300b3eeb7aeb98de166d37d6` | +13559 |
| wash.js | 28091 | `af954e4c449475b6587741d44302c72c744296f4d5405e2406b2d851eaa05751` | 0 (identical) |
| dots.js | 45776 | `87c023035c954e7fd2cd82785ee40dfe83e212cdda9a25ce881fdf9924a56981` | +9229 |
| renderer.js | 1321176 | `4319934870a1f2645944d6600bf561fd5fff660271cb6b2a02b98210cb1262ba` | +1139735 |

Total vendored runtime size: 1,475,807 bytes (previously 312,945; +1,162,862).
`wash.js` is byte-identical to the previous pin; the other four scripts changed.
The five paths are marked `binary` in `.gitattributes`, preventing Git's Windows
line-ending conversion from invalidating these raw-byte hashes on later checkout.

Veusz feature integration and Qt SVG adaptation are separate from these vendored
artifacts. Edit the adapter, not these files; update pins deliberately if upgrading.
