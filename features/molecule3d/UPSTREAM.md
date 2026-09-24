# MolecularRenaissance provenance

- Repository: https://github.com/zhaiyusci/MolecularRenaissance
- Pinned commit: `b351c7b22085ab9c107e4f526c86fc673d3702a6`
- Upstream package: `molplotter`, version `0.2.0` (`private: true`).
- Source: root-level classic runtime artifacts, downloaded as raw bytes from
  `https://raw.githubusercontent.com/zhaiyusci/MolecularRenaissance/b351c7b22085ab9c107e4f526c86fc673d3702a6/<filename>`.
- These five scripts are **unmodified**: no rebuilding, minification, line-ending
  normalization, injected headers, or npm lifecycle scripts.
- Dependency load order: `dot-regions.js`, `boundaries.js`, `wash.js`, `dots.js`,
  `renderer.js`. The renderer exposes `globalThis.MolEngraver` in a classic-script
  runtime, with no DOM or Node required.

## Permission and license status

The user identifies this as their own repository and explicitly authorized its
integration into this workspace as an independent molecule3d feature. No upstream
LICENSE file was found at the pinned commit, and its package metadata specifies
no license. **Upstream license is unspecified.** Author permission for this
integration is not a public license grant: this integration does not invent,
reassign, or claim a license for the upstream artifacts. Preserve upstream notices;
clarify redistribution licensing with the author before independent redistribution.

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
of the host environment still apply; the helper does not bypass them. Initial
sandbox downloads failed TLS authentication; the parent agent retried the exact
command with user-approved access and obtained these bytes.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| dot-regions.js | 27097 | `641597db1605395112e223f8837948d3e5683f7641b545c0f6d0985d440bf647` |
| boundaries.js | 39769 | `4cb52442ab94dcf56962dc89c7aa13b7dc63f802fd8d873caf3e08cd75f9a74f` |
| wash.js | 28091 | `af954e4c449475b6587741d44302c72c744296f4d5405e2406b2d851eaa05751` |
| dots.js | 36547 | `528939c79a007d24e53497f2af0d43852a1a6f0d60163b3440c648805cc15241` |
| renderer.js | 181441 | `339d294c87367656cd9ed70299768db6ee6a1609fcaf1d82cc1f4410304c2fa4` |

Veusz feature integration and Qt SVG adaptation are separate from these vendored
artifacts. Edit the adapter, not these files; update pins deliberately if upgrading.
