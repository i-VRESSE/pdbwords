# Contributing

Static TypeScript app using Mol* and MolViewSpec; Python handles maintenance and
character discovery. Commands run from the repository root.

## Setup

Use Node 24, pnpm 12.9.1, and Python 3.11 (`.python-version`), matching CI.

```sh
pnpm install --frozen-lockfile
uv sync --locked
pnpm dev
```

Open `/pdbwords/` on the dev server. Production preview:

```sh
pnpm build
pnpm exec vp preview --host 127.0.0.1 --port 4173
```

Preview URL: `http://127.0.0.1:4173/pdbwords/`. Rebuild after source changes.
`PAGES_BASE` overrides the build's default `/pdbwords/` base.

## Code map

| Path                               | Purpose                                                        |
| ---------------------------------- | -------------------------------------------------------------- |
| `src/main.ts`, `src/style.css`     | UI and render lifecycle                                        |
| `src/geometry.ts`                  | Validation, layout, MolViewSpec scenes                         |
| `src/renderer.ts`, `src/digits.ts` | Mol* rendering, coordinate cache, assemblies, digit transforms |
| `src/export.ts`                    | Word PNG composition                                           |
| `src/manifest.json`                | Shared geometry and provenance                                 |
| `scripts/`, `scripts/tests/`       | Maintenance, discovery, Python tests                           |
| `src/*.test.ts`, `browser/`        | Unit and browser tests                                         |

## Checks

```sh
pnpm check
pnpm test
uv run ruff check scripts
uv run ruff format --check scripts
uv run pytest
pnpm build
pnpm exec playwright install --with-deps chromium
pnpm test:browser --project=chromium
```

Format/fix with `pnpm exec vp check --fix`, `uv run ruff check --fix scripts`,
and `uv run ruff format scripts`.

Browser tests need RCSB access and WebGL, use port 4173, and write artifacts to
`test-results/`. Stop stale previews before testing. CI runs Chromium; install
Firefox and WebKit to run all projects with `pnpm test:browser`.
`CHROMIUM_PATH` selects an existing executable. Linux full-suite CI settings:

```sh
CI=true LIBGL_ALWAYS_SOFTWARE=1 xvfb-run --auto-servernum pnpm test:browser
```

## README images

Build and start the production preview as above, then in another terminal:

```sh
pnpm run images:readme
```

Requires installed Chromium and RCSB access. The command overwrites:

| File under `docs/images/` | Output                                    |
| ------------------------- | ----------------------------------------- |
| `pdbwords-app.png`        | Full-page screenshot rendering `pdbwords` |
| `alphabet.png`            | Word PNG from “Try all letters (A–Z)”     |
| `digits.png`              | Word PNG from “Try all digits (0–9)”      |

Defaults: rainbow, white background, 20% spacing, 1600 × 900 exports;
1440 × 1000 viewport at device scale 1 for the screenshot.
Set `PDBWORDS_URL` for another preview or `README_IMAGES_DIR` for review output:

```sh
README_IMAGES_DIR=/tmp/pdbwords-readme-images pnpm run images:readme
```

For manual updates, use the example buttons and “Download word PNG”, or render
`pdbwords`, reset the view, and capture the full page. Save to the paths above.
Inspect all outputs and commit affected images with UI, geometry, or rendering
changes. PyMOL asset generation and browser tests do not update README images.

## Letter maintenance

```sh
uv run python scripts/build_letters.py --sessions AlphabetPDB.zip --letters PS
uv run python scripts/extract_manifest.py --sessions AlphabetPDB.zip --letters PS
```

Omit `--letters` for A–Z; omit `--sessions` to download the verified archive.
Tiles go to `assets/`; extraction updates `src/manifest.json`, preserving other
letters and digit definitions. `--theme loop|oval|tube` on the image builder
writes reference tiles under `assets/themes/`.

## Character discovery and digit changes

```sh
pnpm run discover --workdir digit-pilot collect --count 100 --workers 4
pnpm run discover --workdir digit-pilot rank --characters 'AB4?'
pnpm run discover --workdir digit-pilot sheets --top 12
pnpm run discover:angles --workdir digit-pilot --characters 'AB4?' --step 15
```

See [character-search.md](docs/character-search.md) for review, caching, fonts,
and optional vision scoring. Global options precede the subcommand.
`digit-pilot/` is the ignored default cache; discovery does not modify the app.

Update approved definitions in `src/manifest.json`, preserving source cameras,
URLs/hashes, assembly/model/selection, and review provenance. When swapping
assignments, move complete definitions and update review notes.

- PDBe cameras bake rotation into `camera.up`; `rotation_clockwise_deg` is metadata.
- PyMOL cameras apply `image_rotation_clockwise_deg` at runtime; do not also bake
  that rotation into `view`.

Reload after manifest edits to clear geometry/tile caches. Inspect affected glyphs
and mixed text in the scene, both PNG exports, and MolViewSpec. Refresh README
images. New character classes also require validation and renderer/export changes.

`pnpm run measure:coordinates` refreshes letter-source measurements in
`measurements/coordinates.json`; update README measurement claims/dates as needed.

## Contributions and publication

PRs should describe behavior and verification; include previews for visual changes.
Preserve attribution and provenance. Code is [GPL-3.0-or-later](LICENSE); alphabet
assets have [separate non-commercial terms](ASSET_LICENSE.md).

`web-checks.yml` runs on pushes/PRs. Publish through the manual “Publish protein
words” workflow (`pages.yml`) after reviewing `dist/`; GitHub Pages must use the
Actions source. Keep `CITATION.cff` and the README DOI badge consistent.
