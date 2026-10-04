# Digit search pilot

`scripts/digit_search.py` implements the search and review milestone in
[`plan-digits.md`](../plan-digits.md). It produces candidates, not accepted digit
definitions. Numeric input remains rejected until reviewed structures, selections,
camera geometry, and all four themes are available. It never substitutes letters.

## Start small

From the repository, run:

```console
uv run --script scripts/digit_search.py collect --count 10 --workers 2
uv run --script scripts/digit_search.py rank
uv run --script scripts/digit_search.py sheets --top 12
```

The default working directory is `digit-pilot/`, which is excluded from Git and
package assets. Global options must precede the subcommand. For example:

```console
uv run --script scripts/digit_search.py --workdir digit-pilot --offline collect --count 10
```

The RCSB query requests experimentally determined protein polymer entities and
one representative per 30% sequence-identity cluster. A seeded shuffle samples
unique entries. This reduces sequence redundancy; it is a proxy for structural
diversity, not a guarantee of distinct folds. The seed defaults to 2026.
`selection.json` records the query, cached response, entity IDs, and selected
entries. Increasing `--count` with the same seed preserves the smaller sample.
Use `collect --ids 2wcd,1d8c` for an explicit download smoke test.

PDBe catalogues determine filenames and available suffixes. The collector
downloads one coloring for each advertised assembly front/side/top view at the
closest available resolution to 200 pixels. Preferentially it uses chain
coloring. `--size 800` requests higher-resolution images when needed. Each image
record preserves its PDB ID, assembly, model, view, caption, URLs, and SHA-256.
Missing catalogues, views, and failed downloads are recorded in `missing.json`.

PDBe entity scenes can depict multiple copies of the protein in an assembly.
They are deliberately excluded rather than labeled as individual chains.
Independent chain candidates and additional orientations require coordinate
rendering during the refinement stage below.

## Download cache

Every HTTP response is saved to disk before it is read. `cache/` keys are derived
from the URL and, for the RCSB POST, the request body. Successful transfers use an
atomic rename; an interrupted `.part` file is never treated as a cache hit.
Sidecar files record source URLs, request bodies, and file hashes.

Rerunning a command reuses successful downloads. The single sequence-cluster
query is shared across sample sizes, seeds, and collection reruns. Views with
other colorings are not downloaded. HTTP 404/410 responses are negative-cached;
use `--retry-missing` to check those URLs again. Transient errors use bounded
retries and backoff and do not become permanent negative-cache entries.
`--offline` prohibits downloads entirely and reports absent cached files.
To intentionally refresh a successful response, remove its particular cache
file and sidecar; there is no automatic expiration of the reproducible snapshot.

Keep the same workdir to reuse the cache. Changing sample parameters rewrites
the selection and image index, but retains all previously downloaded files.
Keep review CSVs with the matching ranking snapshot.

## Ranking and vision comparison

`rank` reports processed image counts, percentage, elapsed time, estimated time
remaining, and normalization failures every 25 images or five seconds (after
the current image completes). It also announces vision model loading, reports
vision scoring progress, and announces when it writes the rankings file. Output
is flushed immediately so progress remains visible when redirected or piped.

`rank` crops background, preserves aspect ratio, and removes small disconnected
components, including small axis widgets in PDBe's lower-left corner. It saves a
normalized cartoon and a silhouette for each image. Captions and source labels
never enter scoring. Attached axes, detached protein fragments, and unusually
small structures can still need manual inspection: normalization is a heuristic.

The inexpensive baseline compares silhouettes with glyph templates using
intersection over union. It evaluates all ten digits plus O, I, S, B, and Z.
Different stroke widths accommodate thick cartoons. `--font PATH` may be repeated
to benchmark additional fonts; otherwise Pillow's bundled font is used.
The baseline's `none` score is `1 - best glyph IoU`, an explicit abstention
heuristic. These scores are not probabilities or acceptance decisions.

An optional local CLIP backend scores both cartoons and silhouettes, including
a text prompt for no recognizable digit or letter. Install its additional
dependencies only when actually comparing a vision model:

```console
uv run --with torch --with transformers python scripts/digit_search.py rank --vision-model /path/to/cached/clip-model
uv run --script scripts/digit_search.py sheets --method vision_cartoon --top 12
uv run --script scripts/digit_search.py sheets --method vision_silhouette --top 12
```

A Hugging Face model identifier also works, but requires downloading model
weights. Use a local model snapshot for reproducible, download-free comparison;
`--offline` also sets `local_files_only` for model loading. Raw CLIP logits are
recorded without softmax and must not be compared numerically to template IoUs.
The backend automatically uses CUDA when available, processes 32 candidate pairs
per batch, and computes text embeddings once. It reports the selected device.
It also writes `vision_glyph` scores: cosine similarity between CLIP embeddings
of protein silhouettes and rendered digit/letter references. References use
Pillow's default font plus available DejaVu Sans, Sans Mono, and Serif fonts,
with three stroke widths. This method has no automatic `none` score; visual
review determines whether a candidate is recognizable. Generate its sheets with
`sheets --method vision_glyph --top 10`. Numeral text prompts can return almost
identical rankings for different digits, so inspect results before interpreting
them as digit recognition.
The useful comparison is the number of clearly readable candidates in the
first k results, measured against the same human judgments.

## Human review and shortlist

`sheets` creates ten PNG contact sheets under `sheets/METHOD/`, a
`shortlist.json` mapping each digit to candidate IDs, and `reviews.csv`.
Digits with nonempty entries in `reviewed-shortlist.json` are automatically
excluded from new sheets and shortlists. Use `--digits 1234569` to restrict the
remaining targets further. Existing sheets and review CSVs are retained.
Each sheet contains cartoons, silhouettes, source identifiers, the target score,
and the highest-scoring competing label. One view per assembly is included,
so three views of one assembly cannot occupy three shortlist positions.
Existing review files are never overwritten.

For each reviewed row, fill in:

| Field | Value |
| --- | --- |
| `readable` | `yes` or `no`; leave blank if unreviewed |
| `confusable` | A competing letter/digit if ambiguity remains; otherwise blank |
| `reviewer` | The human reviewer's name or identifier |
| `notes` | Readability at normal tile size, selection concerns, angle suggestions |

Merge judgments from different methods into one CSV, with one row per
digit/candidate pair, to compare against a common reference. Then run:

```console
uv run --script scripts/digit_search.py benchmark --reviews digit-pilot/sheets/template/reviews.csv --top 12
```

`benchmark.json` reports review coverage, readable counts, and precision at k
for each available method and digit. Precision remains `null` until every
candidate in that top-k list has been reviewed. A candidate marked readable but
confusable is not counted as clearly readable. `reviewed-shortlist.json` includes
only human-reviewed, readable, unconfusable candidates. An empty review CSV
produces an empty shortlist, not inferred acceptance.

Fetch saved states and captions only for promising candidates:

```console
uv run --script scripts/digit_search.py fetch-shortlist --shortlist digit-pilot/reviewed-shortlist.json --coordinates
```

`--coordinates` additionally caches RCSB biological assembly mmCIFs. Repeated
views of the same assembly share one cached coordinate download. States and
captions are requested only when their suffixes are advertised by the catalogue.
Paths and failures are saved to `shortlist-downloads.json`. To investigate
unreviewed ranked candidates, pass the corresponding `sheets/METHOD/shortlist.json`
instead, or reduce that file to a few candidate IDs first.

## Refinement and integration gate

Search rigid in-plane rotations of the cached views for still-missing digits:

```console
uv run --script scripts/digit_angle_search.py --step 10 --output digit-pilot/angle-search
```

This command skips digits already present in `reviewed-shortlist.json`, also
excludes their PDB entries, and compares thin font references across viewing
rotations. Known digits remain competing shape classes to reject confusions.
It filters very dense silhouettes, ranks target IoU plus its margin over other
glyphs, and keeps one candidate per PDB entry on each sheet. All rotations are
rigid; it does not mirror, stretch, or edit coordinates. Results are provisional.
Outputs include contact sheets, candidate PNGs, a review template, and source
metadata with the exact clockwise angle. Use a new output directory for each
search snapshot. `--rankings PATH` can supply an expanded or independently
rendered dataset, whose image and silhouette paths are relative to the workdir.
Use `--digits 45` to search only for 4 and 5; the approved-digit exclusions still
apply. `--workers 8` parallelizes image scoring while preserving deterministic
ranking and output order.
For an exploratory search favoring open outlines, use `--max-occupancy 0.4`.
The default limit is 0.68; occupancy is measured before in-plane rotation.
This filter can also discard useful structures and does not establish readability.

The discovery run also sampled intact chains and assembly viewing angles in
PyMOL. The reusable scripts cover collection, ranking, and in-plane rotation
search; custom 3D exploration remains in the local pilot artifacts.
For promising entries, load the cached assembly mmCIF (its assembly transforms
are already applied), or deposited coordinates for an intact chain. Sample
viewing directions and in-plane rotations; avoid modifying molecular geometry
or deleting residues to manufacture a digit.

An accepted definition must preserve the PDB ID, source URL and hash, model,
assembly, exact chain/residue selection, any assembly operators, saved camera
rotation, projected center and bounds, and proportional advance. Record human
review results and representative previews alongside the definition. The
existing letter manifest is the reference for geometry fields; assembly
geometry also needs explicit reconstruction metadata.

Only after these definitions are accepted should they enter the shared
manifest/provenance mapping, generate classic/loop/oval/tube tiles, enable digit
validation, and extend MolViewSpec to reconstruct identical selections and
assembly geometry. Validate `0123456789` and `AI 2026` at normal output sizes,
including numeric provenance, asset completeness, and static/3D consistency.
All ten digits now have user-approved selections in the shared manifest
under `digits`, including source cameras, rotations, and review provenance.
Digit 6 retains its saved PyMOL view and subsequent clockwise image rotation.
Static digit tiles, projected layout geometry, and application support for
assembly reconstruction remain to be implemented before enabling numeric input.

## Verified small run

On 2026-09-30 the 10-entry, seed-2026 live run produced 36 assembly views with
no missing downloads. Template ranking and all ten contact sheets were generated.
Collection was then repeated with `--offline` to verify disk cache reuse.
This smoke test verifies the workflow; it does not validate digit resemblance.
At the time of this initial smoke test, vision weights had not been downloaded.
Subsequent searches used local CUDA CLIP scoring, expanded to 82,116 views from
18,553 PDB entries, and obtained explicit user approvals for all ten digits.

Sources: [RCSB Search API](https://search.rcsb.org/),
[PDBe catalogue example](https://www.ebi.ac.uk/pdbe/static/entry/2wcd.json),
[PDBe PDBImages pipeline](https://github.com/PDBeurope/pdb-images).
