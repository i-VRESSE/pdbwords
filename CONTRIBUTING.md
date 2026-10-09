# Contributing to pdbwords

pdbwords is a static TypeScript webapp using Mol* and MolViewSpec. Python supports
asset maintenance and character discovery. Run the commands below from the
repository root. The app needs WebGL and internet access to RCSB PDB; discovery
also uses PDBe. There is no backend service to start.

## Set up a development checkout

Use Node 24 and pnpm 12.9.1, matching CI. `package.json` records the pnpm version
and minimum supported Node version. Install [uv](https://docs.astral.sh/uv/) for
Python work; `.python-version` selects Python 3.11, and the maintenance project
supports Python 3.11–3.13.

```sh
git clone https://github.com/i-VRESSE/pdbwords.git
cd pdbwords
pnpm install --frozen-lockfile
uv sync --locked
pnpm dev
```

Open the URL printed by Vite with `/pdbwords/` appended, usually
`http://localhost:5173/pdbwords/`. Source edits reload automatically. Python
installation is needed for the maintenance scripts and their tests; the webapp
build uses only JavaScript dependencies. Do not edit `pnpm-lock.yaml` or `uv.lock`
by hand. When deliberately changing dependencies, update the corresponding
package file and regenerate its lockfile with pnpm or uv.

To inspect the production build:

```sh
pnpm build
pnpm exec vp preview --host 127.0.0.1 --port 4173
```

Open `http://127.0.0.1:4173/pdbwords/`. Rebuild after changing source files; the
preview serves `dist/`. Vite defaults to the `/pdbwords/` base path. For another
hosting path, set `PAGES_BASE` when building:

```sh
PAGES_BASE=/ pnpm build
```

Keep the default base when running the configured browser tests.

## Where to make changes

| Path                                         | Responsibility                                                           |
| -------------------------------------------- | ------------------------------------------------------------------------ |
| `index.html`, `src/main.ts`, `src/style.css` | App entry point, controls, render lifecycle, styling                     |
| `src/geometry.ts`                            | Manifest validation, text parsing, wrapping, spacing, MolViewSpec scenes |
| `src/renderer.ts`                            | Mol* viewers, coordinate cache, biological assemblies, image capture     |
| `src/digits.ts`                              | Digit camera transforms, measured bounds, normalized coordinates         |
| `src/export.ts`                              | Word PNG composition and tile caching                                    |
| `src/manifest.json`                          | Shared letter geometry, digit definitions, source and review provenance  |
| `src/*.test.ts`                              | JavaScript unit tests                                                    |
| `browser/`                                   | Production-browser rendering, exports, spacing, and failure tests        |
| `scripts/`, `scripts/tests/`                 | Maintenance and discovery tools and Python tests                         |
| `assets/`                                    | Original letter/reference tiles and punctuation PNGs                     |
| `docs/images/`                               | Images embedded in the README                                            |
| `measurements/coordinates.json`              | Recorded live coordinate measurements                                    |
| `vite.config.ts`, `playwright.config.ts`     | Build/check settings and browser test configuration                      |
| `.github/workflows/`                         | CI checks and manual GitHub Pages publication                            |

The browser imports `src/manifest.json` directly. Letter scenes select author
chain identifiers from that manifest. Digits reconstruct biological assemblies,
measure their selected protein geometry, and normalize their heights to A.
Letter exports use remote coordinate URLs; digit MolViewSpec exports embed scaled
BCIF coordinates so they remain portable. Changes to scene geometry must also
work in word PNG, scene PNG, and MolViewSpec exports.

## Checks before submitting a change

Run the checks that cover your change. This is the CI command set:

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

`pnpm check` runs formatting, lint, and TypeScript checks. To fix formatting and
supported lint issues, use `pnpm exec vp check --fix`. For Python, use
`uv run ruff check --fix scripts` and `uv run ruff format scripts`.
Review automatic fixes before committing.

Browser tests start a production preview on port 4173, or reuse an existing one
outside CI. Stop an old preview or rebuild it to avoid testing stale files.
Live rendering tests need RCSB access and can take several minutes. Failure
screenshots and other test outputs go under ignored `test-results/`; CI uploads
that directory when checks fail. `CHROMIUM_PATH=/path/to/chromium` selects an
existing Chromium executable.

For all configured browsers, install Chromium, Firefox, and WebKit:

```sh
pnpm exec playwright install --with-deps chromium firefox webkit
pnpm test:browser
```

The projects are `chromium`, `firefox`, and `mobile` (iPhone WebKit). CI currently
runs Chromium only. To run the full suite with CI settings on Linux, provide
Xvfb and Mesa software rendering:

```sh
CI=true LIBGL_ALWAYS_SOFTWARE=1 xvfb-run --auto-servernum pnpm test:browser
```

For a focused check:

```sh
pnpm exec vp test run src/digits.test.ts
uv run pytest scripts/tests/test_character_search.py
pnpm exec playwright test browser/app.spec.ts --project=chromium
```

Add tests for new behavior or regressions where they provide useful coverage.
For appearance changes, inspect the actual rendered structures and exports;
a passing geometry test does not establish that a structure resembles a glyph.

## Update the images in README.md

The README embeds three repository images:

| File                           | Content                            | How it is produced                              |
| ------------------------------ | ---------------------------------- | ----------------------------------------------- |
| `docs/images/pdbwords-app.png` | App interface rendering `pdbwords` | Full-page browser screenshot                    |
| `docs/images/alphabet.png`     | A–Z across four lines              | Download word PNG after “Try all letters (A–Z)” |
| `docs/images/digits.png`       | 0–9 across two lines               | Download word PNG after “Try all digits (0–9)”  |

The DOI badge is hosted externally; it is not a local PNG to regenerate.
The alphabet and digit PNGs use the app's live Mol* rendering. Rebuilding the
PyMOL tiles in `assets/` does not regenerate these README images.

### Regenerate all three with one command

Install the JavaScript dependencies and Chromium, then build and start a preview
in one terminal:

```sh
pnpm install --frozen-lockfile
pnpm exec playwright install --with-deps chromium
pnpm build
pnpm exec vp preview --host 127.0.0.1 --port 4173
```

Leave that terminal running. In a second terminal, from the repository root:

```sh
pnpm run images:readme
```

`scripts/update-readme-images.mjs` opens Chromium, waits for completed rendering,
captures the app with the message `pdbwords`, and exports the alphabet and digits.
It overwrites the three files listed above. Settings come from a fresh app page:
residue rainbow, paper white, 20% spacing, and 1600 × 900 word PNGs. The app
screenshot uses a 1440 × 1000 CSS-pixel viewport at device scale 1 and captures
the full page. Example buttons supply these exact line breaks:

```text
ABCDEFG
HIJKLMN
OPQRSTU
VWXYZ
```

```text
01234
56789
```

The script requires a running preview and live RCSB access. It fetches coordinates
through Node in the same way as the browser tests, supports `CHROMIUM_PATH`, and
closes its browser when finished. It does not start the server or build the app.
For another preview URL or an output directory for review:

```sh
PDBWORDS_URL=http://127.0.0.1:4173/pdbwords/ README_IMAGES_DIR=/tmp/pdbwords-readme-images pnpm run images:readme
```

Open each PNG and inspect the layout, glyph orientations, colors, and resolution.
Check that no structures are missing or clipped and the screenshot contains a
finished scene. Include updated PNGs with changes to the interface, letter or
digit assignments, camera orientations, colors, spacing, or export rendering.
Keep the existing paths so README links continue to work.

### Update an individual image manually

Open a freshly built app with the same settings listed above.

- For `alphabet.png`, click “Try all letters (A–Z)”, wait for “26 protein letters
  ready”, then click “Download word PNG”. Save the downloaded `pdbwords-word.png`
  as `docs/images/alphabet.png`.
- For `digits.png`, click “Try all digits (0–9)”, wait for “10 protein characters
  ready”, then click “Download word PNG”. Save the download as
  `docs/images/digits.png`.
- For `pdbwords-app.png`, enter `pdbwords`, click “Render protein words”, wait for
  “8 protein letters ready”, and click “Reset view”. Capture the browser page at
  the viewport above, including the controls and source links, without browser
  chrome. Save the screenshot as `docs/images/pdbwords-app.png`.

“Download scene PNG” captures the current molecular camera without the app
interface. “Download word PNG” composes normalized glyph tiles. Use the output
specified in the table for each image. Browser-test screenshots remain in
`test-results/` and do not automatically update README images.

## Update letter assets and geometry

The original A–Z views come from official Howarth PyMOL sessions. The tools
download and verify `AlphabetPDB.zip` when `--sessions` is omitted. To use an
existing archive or extracted session directory:

```sh
uv sync --locked
uv run python scripts/build_letters.py --sessions AlphabetPDB.zip
uv run python scripts/extract_manifest.py --sessions AlphabetPDB.zip
```

The image builder defaults to 1000-pixel-high transparent classic PNGs in
`assets/`. It checks source PDB IDs against the manifest. The extractor reads
protein cartoons shown in the sessions, excludes hidden chains, and uses letter
tile proportions for spacing. It updates `src/manifest.json` while preserving
manually reviewed digit definitions and letters outside the requested subset.

To refresh only P and S:

```sh
uv run python scripts/build_letters.py --sessions AlphabetPDB.zip --letters PS
uv run python scripts/extract_manifest.py --sessions AlphabetPDB.zip --letters PS
```

For reference tiles in another PyMOL theme:

```sh
uv run python scripts/build_letters.py --sessions AlphabetPDB.zip --theme tube
```

Themes are `classic`, `loop`, `oval`, and `tube`; alternative themes are written
under `assets/themes/`. The browser uses its own rainbow/ocean styles. Inspect
`--help` for output directories, image dimensions, and manifest paths. After
extracting geometry, format `src/manifest.json`, run the applicable checks, and
regenerate the README images from a new build.

## Find or change character structures

See [the character discovery guide](docs/character-search.md) for cache behavior,
optional vision models, review CSVs, benchmarking, and coordinate downloads.
A small discovery run is:

```sh
pnpm run discover --workdir digit-pilot collect --count 100 --workers 4
pnpm run discover --workdir digit-pilot rank --characters 'AB4?'
pnpm run discover --workdir digit-pilot sheets --top 12
pnpm run discover:angles --workdir digit-pilot --characters 'AB4?' --step 15
```

Each character is a separate target; case is preserved. `--font PATH` supplies
fonts for custom glyphs. Global options such as `--workdir` and `--offline`
precede the discovery subcommand. `digit-pilot/` is the historical default cache
directory and is ignored by Git. Reuse it for offline runs. Keep matching ranking
snapshots and human judgments together; avoid committing large caches or model
weights. Discovery tools do not add glyphs to the webapp automatically.

For an approved digit, update its entry in `src/manifest.json` with the PDB ID,
assembly, model, protein selection, camera, source URLs and hashes, and review
provenance. Preserve the source camera so the displayed orientation can be
reconstructed. The runtime currently supports A–Z, 0–9, and the existing
punctuation behavior. New character classes require updates to text validation,
manifest handling, rendering, and exports as well as a discovered structure.

### Change a digit's orientation

There are two camera formats:

- PDBe-style cameras store `position`, `target`, and `up`. The saved `camera.up`
  already includes the intended in-plane rotation. The sibling
  `rotation_clockwise_deg` records that rotation relative to `source.camera`;
  changing only that metadata field does not rotate the rendered digit.
- PyMOL cameras store `format: "pymol"`, an 18-number `view`, and
  `image_rotation_clockwise_deg`. `digitRotation()` applies that image rotation
  at runtime; avoid also baking it into the view.

To roll a PDBe camera clockwise by angle θ from its source view, compute the
unit viewing axis `z = normalize(position - target)`, the unit right axis
`x = normalize(cross(up, z))`, and set `camera.up = cos(θ) * up - sin(θ) * x`
using the source up vector. Keep the position and target unchanged and record
the total clockwise angle in degrees. For a new adjustment, calculate from the
source camera or deliberately account for the rotation already saved.

When swapping glyph assignments, move the complete definitions, including their
source records, and update review notes to explain the new assignments. Reload
the browser after editing the manifest: resolved geometry and tiles are cached
for the page session. Check the affected characters individually, in mixed
text, and in all three exports. Regenerate `docs/images/digits.png` when changing
digit shapes or rotations.

## Refresh coordinate measurements

```sh
pnpm run measure:coordinates
```

This downloads the manifest's letter BCIF sources and rewrites
`measurements/coordinates.json` with sizes, SHA-256 hashes, download timings,
CORS headers, author-chain CA ranges, and secondary-structure counts. It measures
letters, not the separate digit definitions. The records describe a live snapshot;
they do not pin runtime downloads. Inspect changes and update any associated
measurement claims and dates in the README when publishing a new snapshot.

## Submit and publish

Keep changes focused and explain the resulting behavior, relevant verification,
and any remaining limitations in the pull request. Include appearance previews
when changing glyphs or rendering. Update documentation when changing commands,
app controls, supported characters, or source provenance. Commit source files,
lockfiles when dependencies change, and intentional documentation assets.
Generated `dist/`, browser reports, `.venv/`, `node_modules/`, and discovery caches
are ignored and should remain local.

`.github/workflows/web-checks.yml` runs on pushes and pull requests.
`.github/workflows/pages.yml` publishes through a manual workflow dispatch:
enable GitHub Pages with the Actions source, review the production build and
attribution, then run “Publish protein words” for the intended branch. Pushes do
not automatically publish the site. The build includes `LICENSE` and
`ASSET_LICENSE.md` in `dist/`. There is no Python wheel or PyPI release workflow.
Keep `CITATION.cff` and the README DOI badge consistent when updating citation
metadata.

Application and maintenance code are GPL-3.0-or-later; see [LICENSE](LICENSE).
Howarth alphabet images have separate non-commercial terms; see
[ASSET_LICENSE.md](ASSET_LICENSE.md). Preserve the app's attribution and coordinate
source links, and record provenance for newly curated structures.

## Troubleshooting

| Symptom                                             | What to check                                                                                           |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Blank page or missing assets                        | Open the configured `/pdbwords/` path; check `PAGES_BASE` and rebuild                                   |
| A source edit does not appear                       | The production preview serves the last build; rebuild and reload                                        |
| Glyph changes appear inconsistent                   | Reload to clear resolved digit geometry and export tile caches                                          |
| WebGL unavailable                                   | Enable browser hardware acceleration; browser tests use Chromium software rendering                     |
| Coordinate download error                           | Check RCSB availability, internet/proxy access, and the URL in the error; retry                         |
| Missing Playwright executable                       | Install the browser binaries; use `--with-deps` for Linux system libraries                              |
| Check fails on an unrelated local file              | Inspect the reported path; format checks scan local files, including untracked documents                |
| Discovery says a character is missing from rankings | Rerun `rank --characters` with the required targets before generating sheets                            |
| Discovery has no usable images                      | Inspect `missing.json`; use the same workdir and check cache/offline options                            |
| uv dependency resolution fails                      | Use the Python version pinned in `.python-version`; PyMOL requires the project's supported Python range |
