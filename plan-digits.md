# Finding protein structures shaped like digits

## Objective

Find recognizable protein structures for digits 0–9 and add them to pdbwords.
Each accepted digit needs a reproducible structure selection and viewing angle,
static assets for the four existing themes, and geometry for the interactive 3D
renderer.

Digit input is currently explicitly rejected by `_reject_digits()` in
`src/pdbwords/__init__.py`. The existing alphabet has saved chain selections and
camera rotations in `src/pdbwords/assets/manifest.json`. Reliable digit support
requires similarly curated structures; earlier letter-shaped substitutions were
rejected because they did not read reliably as digits.

## Findings from the initial investigation

An image-based search is feasible. The best starting point appears to be PDBe's
existing structure images, which provide multiple views and downloadable Mol*
states.

The following downloads were verified successfully using entry `2WCD` as a test:

- [PDBe image catalogue](https://www.ebi.ac.uk/pdbe/static/entry/2wcd.json).
  Lists assembly images, filenames, descriptions, and available suffixes.
- [Assembly 2, top view, 800 × 800 PNG](https://www.ebi.ac.uk/pdbe/static/entry/2wcd_assembly_2_chain_top_image-800x800.png).
- [Matching Mol* state](https://www.ebi.ac.uk/pdbe/static/entry/2wcd_assembly_2_chain_top.molj).
- [RCSB assembly JPEG](https://cdn.rcsb.org/images/structures/2wcd_assembly-1.jpeg).

The test entry establishes the download route; it is not an accepted digit.

For the PDBe catalogue, image suffixes are inside the entry object:
`catalogue[pdb_id]["image_suffix"]`. The tested catalogue offers PNG sizes of
100, 200, 800, and 1600 pixels, plus `.caption.json` and `.molj` files. Construct
URLs by combining the image record's `filename` with an available suffix under
`https://www.ebi.ac.uk/pdbe/static/entry/`. Discover filenames and sizes from the
catalogue rather than assuming every entry has the same outputs.

[PDBe's open-source PDBImages pipeline](https://github.com/PDBeurope/pdb-images)
generates images from mmCIF or BinaryCIF coordinates. It supports front, side,
and top views, assembly images, and saved viewer states. This provides a fallback
when existing images are unavailable.

The relevant EBI FTP paths inspected contain coordinate files, assembly metadata,
sequences, and analysis data:

- [PDB archive](https://ftp.ebi.ac.uk/pub/databases/pdb/).
- [Assembly coordinates](https://ftp.ebi.ac.uk/pub/databases/pdb/data/assemblies/mmCIF/).
- [PDBe data](https://ftp.ebi.ac.uk/pub/databases/msd/).
- [PDBe assembly metadata](https://ftp.ebi.ac.uk/pub/databases/msd/assemblies/split/wc/2wcd/).

No bulk rendered-image archive was found in the paths inspected. This was a
targeted inspection, not an exhaustive search. Use `lftp` for further browsing,
restricting listings to specific paths and individual entries because broad
directories contain too many entries.

## Proposed workflow

### 1. Build a small pilot dataset

Start with approximately 1,000 diverse experimentally determined protein
structures. Select entries through the [RCSB Search API](https://search.rcsb.org/),
favoring structural diversity over many near-identical entries. Keep biological
assemblies and individual protein chains as separate search candidates.

Download PDBe catalogues and available assembly views at 200 or 800 pixels.
Initially use one coloring scheme per scene to avoid duplicate downloads.
Cache responses, limit concurrency, retry transient failures, and record missing
images. Preserve PDB ID, assembly, view, source URL, and caption with each image.
Fetch Mol* states only for promising candidates.

### 2. Benchmark digit resemblance

Compare a vision model with silhouette/template matching on the pilot dataset.
Possible starting points include CLIP-style image/text similarity and a vision
language model evaluating shortlisted images. These are proposed approaches;
their accuracy on protein cartoons has not been measured.

Score all ten digits and include a "no recognizable digit" alternative. Include
confusable letters such as O, I, S, B, and Z during evaluation so the search does
not simply reproduce the rejected letter substitutions. Do not interpret model
similarity scores as calibrated probabilities.

Evaluate both the original cartoon and a normalized silhouette. Crop margins,
preserve aspect ratio, and remove axis indicators where present. Avoid allowing
labels or captions to influence the model's judgment of the molecular shape.

Use human-reviewed examples to assess the ranking before expanding the dataset.
The useful measure is how many clearly readable candidates appear near the top
of each digit's ranking, rather than whether the model assigns every image a
digit.

### 3. Review and refine viewing angles

Generate contact sheets of the best candidates for each digit. Review them for
immediate readability, distinction from letters and other digits, and suitability
at the normal pdbwords tile size.

Download coordinates for promising structures and render additional orientations
in PyMOL. Three standard views can miss useful shapes. Sample viewing directions
and in-plane rotations, then refine around promising angles. Explore intact
protein chains or biological assemblies and document any residue selection.
Avoid distortions or arbitrary deletion of residues solely to draw a digit.

Render shortlisted selections using pdbwords' rainbow cartoon style. Confirm
that the resemblance survives the classic, loop, oval, and tube themes.

### 4. Curate reproducible digit definitions

For each accepted digit, record:

- PDB ID, model, assembly, and chain or residue selection.
- Assembly transformations if required to reconstruct the selection.
- Camera rotation, projected center and bounds, and proportional spacing.
- Source coordinates and image provenance.
- Human review results and representative previews.

The search result is a structure plus selection and viewing angle, not merely a
PDB ID. Treat digit definitions as curated assets analogous to the existing
letter definitions.

### 5. Integrate with pdbwords

Once reliable digit definitions are available:

- Extend the shared manifest and provenance mapping to include digits.
- Extend asset generation to render digit tiles for all four themes.
- Update character validation and layout to accept supported digits.
- Ensure the MolViewSpec renderer reconstructs the same selections and assembly
  geometry used for static tiles.
- Update documentation and add meaningful checks for numeric input, provenance,
  asset availability, and static/3D selection consistency.

Validate complete numeric strings as well as isolated digits. In particular,
inspect `0123456789` and mixed text such as `AI 2026` at normal output sizes.

## Next milestone and limitations

The next milestone is a pilot dataset, ranked contact sheets, and a reviewed
shortlist per digit. Expand the search only after the pilot demonstrates useful
rankings.

The download route has been verified. No vision search has been run, no reliable
digit set has been identified, and there is no evidence yet that every digit can
be represented clearly by a suitable protein structure.
