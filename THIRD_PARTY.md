# Third-party components and licences

This project is distributed under the **Apache License 2.0** (see `LICENSE`).

First-party source is Apache-2.0. Third-party bundles retain their upstream
licences and notices, including the licences of any bundled dependencies:

| Artefact | What it is | Licence |
|---|---|---|
| `veusz_js_engine.py`, `jsapi.js` | the platform itself | **Apache-2.0** (this project) |
| `qjs.dll` / `libqjs.so` / `libqjs.dylib` | QuickJS, built unmodified from quickjs-ng 0.16.2 | **MIT** — text in `licenses/quickjs-ng-LICENSE.txt` |
| `features/mathjax/mathjax.js` | MathJax 4.1.3 + font packages, bundled by esbuild | **Apache-2.0** — text in `licenses/mathjax-Apache-2.0.txt` |
| `features/mathjax/fonts/*.js` | one font's data per file, read only when that font is chosen | **Apache-2.0** for the official MathJax fonts; **OFL-1.1** / **GUST** for the fonts converted here (see `licenses/`) |
| `features/katex/katex.min.js` | KaTeX 0.18.7, unmodified | **MIT** — text in `features/katex/LICENSE-KATEX.txt` |
| `features/smiles/smiles-drawer.js` | SmilesDrawer 2.4.1, unmodified npm bundle; includes chroma-js 2.4.2 | **MIT**, **BSD-3-Clause**, and **Apache-2.0** ColorBrewer data; notices in `features/smiles/LICENSE-*.txt` and the bundle |
| `features/smiles/headless.js`, `features/smiles/feature.js` | SMILES adapter and feature | **Apache-2.0** (this project) |
| `features/*/feature.js` | a feature, written against this platform | whatever its author says |
| esbuild | build tool | MIT, used to build the MathJax bundle; not redistributed |

`qjs.dll` is upstream's own build (`cmake -DBUILD_SHARED_LIBS=ON` on an
unmodified quickjs-ng checkout), so "unmodified, MIT" is a property of the file
rather than a claim about a build recipe. The revision used for a published
binary is recorded in the release notes.

## Are these licences compatible?

The bundled permissive components can be redistributed together while retaining
their respective notices:

* **MIT** (QuickJS, KaTeX, SmilesDrawer) and **BSD-3-Clause** (chroma-js) are
  permissive, non-copyleft licences. Keep the original notices and disclaimers.
* **Apache-2.0** (this project, MathJax) is lax and non-copyleft too. It is
  *not* a copyleft licence: it does not require derivative works to be licensed
  the same way. Its extra conditions compared with MIT are paperwork plus a
  patent grant — keep the notices, mark modified files, propagate a `NOTICE`
  file if the original had one (MathJax ships none), no trademark rights, and
  the patent licence ends if you sue the project over patents.
* **OFL-1.1** and the **GUST Font License** (the converted fonts) are
  font licences: they require a modified version to be renamed, which is why
  three of the fonts here are called Sans 1, Sans 2 and Sans 3. They are
  compatible with the rest; the font files are separate artefacts.
* **Veusz** is GPL-2.0-or-later, and is **not redistributed here**. This
  distribution contains no Veusz source code; the plugin loads Veusz at run time
  through its plugin interface, like any other Veusz plugin. Should someone
  redistribute this plugin together with Veusz, that combination is fine as
  well: the Apache-2.0 terms are GPL-compatible (GPLv3 directly, GPLv2 via "or
  later"), so the combination can be passed on under the GPL.

## What a release must contain

1. `LICENSE` — Apache-2.0 (this project).
2. `NOTICE` — attribution for MathJax, mhchemParser, the converted fonts,
   KaTeX, SmilesDrawer, chroma-js/ColorBrewer and QuickJS.
3. `THIRD_PARTY.md` — this file.
4. `licenses/` — the notices above, so `features/` is self-describing if it is
   separated from the rest.
5. `qjs.dll`, `veusz_js_engine.py`, `jsapi.js`, `features/`.

## The fonts

Two kinds of font live in `features/mathjax/`:

* `mathjax.js` carries two fonts inside it (Computer Modern, and one more), so a
  fresh install draws a formula with no font files at all.
* `fonts/` holds **one data file per font**, twenty of them. They are not part
  of `mathjax.js`: each registers a single font's data into the MathJax the
  feature already loaded, and is read **only when that font is chosen** —
  measured, 0.03 s for the 0.9 MB one and 0.31 s for the 10.9 MB one.

The official MathJax font packages are Apache-2.0 like MathJax itself. The other
fonts are converted from their OpenType originals by a change of format only
(the glyph outlines and metrics are the font's own), and keep their own licences:
Lete Sans Math, Luciole Math, Euler Math, Pennstander Math, GFS Neohellenic Math
and IBM Plex Math under OFL-1.1; the one built on New Computer Modern under the
GUST Font License.

## Generated data

`features/mathjax/mathjax.js` is **generated**: MathJax is bundled and minified
with esbuild, and the glyph ranges are inlined because the embedded engine
cannot fetch anything at render time (QuickJS is synchronous, and MathJax's
on-demand font loading has no `Promise` to retry with). The builder prepends a
banner naming the packages and the licence, so the file carries its own
provenance:

```
@mathjax/src@4.1.3
@mathjax/mathjax-newcm-font@4.1.3        (or another official font)
@mathjax/mathjax-mhchem-font-extension@4.1.3
@mathjax/mathjax-bbdx-font-extension@4.1.3
@mathjax/mathjax-dsfont-font-extension@4.1.3
@mathjax/mathjax-bbm-font-extension@4.1.3
esbuild
```

`qjs.dll` is generated too, by upstream's own build — see above.
