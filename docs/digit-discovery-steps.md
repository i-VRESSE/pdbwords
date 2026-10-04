# Steps taken to find all ten protein digits

This records the discovery work completed on 2026-10-04. The final definitions
are in `src/pdbwords/assets/manifest.json`, under `digits`. All ten were explicitly
approved by the user. The local working data and reviewed shortlist remain in
`digit-pilot/`, which is intentionally excluded from Git.

## Search and review process

1. Established a cached download pipeline for PDBe assembly image catalogues,
   front/side/top images, matching Mol* states, and RCSB biological assembly
   coordinates. Recorded source identifiers, URLs, SHA-256 hashes, failures,
   and dataset selection provenance.
2. Built a pilot of 13,068 assembly views from 2,990 PDB entries. Normalized
   cartoons and silhouettes without changing aspect ratio, and compared them
   against digit glyphs and confusable letters O, I, S, B, and Z.
3. Downloaded CLIP ViT-B/32, revision
   `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268`, and ran it on the 6 GB NVIDIA
   RTX 3050. Used batched CUDA scoring and cached text embeddings. Compared
   text prompts, cartoons, silhouettes, and image embeddings of font glyphs.
   CLIP scores were insufficiently specific to determine acceptance.
4. Generated top-ten contact sheets and performed direct AI visual review.
   Recorded the user's initial approvals for 0, 7, and 8 separately from
   provisional AI judgments.
5. Added rigid in-plane rotation search using silhouette intersection over
   union and a margin against competing digits and letters. Excluded already
   approved digits and their source PDB entries from subsequent searches.
   Used density filters to explore more open outlines. Scores were never
   treated as probabilities.
6. Expanded to 33,099 views from 7,497 entries, then 56,253 views from 12,489
   entries, and 77,703 views from 17,453 entries. Downloaded larger previews
   and source states/coordinates for promising results. Sampled additional
   3D orientations of intact protein chains or biological assemblies in
   PyMOL, without stretching, mirroring, or deleting residues to draw digits.
7. Identified 9GC7 assembly 2 as the strongest 3 lead. Saved its PDBe front
   view rotated 270 degrees clockwise and separately rendered a refined
   camera in classic, loop, oval, and tube themes. The user ultimately
   approved the PDBe preview, rather than the refined rainbow camera.
8. Found 9LWI assembly 1, front view rotated 80 degrees clockwise, in
   `digit-pilot/search-45-02/sheets/4.png`; the user approved candidate 1 as 4.
9. For 5, examined the existing S, J, C, W, Z, and G letter structures as
   family seeds: 2OT8, 1B3U, 2BNH, 4CJ9, 4BTA, and 4U48. Searched repeat-rich
   and related families and additional native orientations. Added 4,413
   views from 1,100 previously unseen entries, reaching a combined dataset
   of 82,116 views from 18,553 entries.
10. The user selected 8OR3 assembly 1, front view rotated 90 degrees clockwise,
    as 5. Then explicitly approved the first offered previews for 1, 2, 3,
    6, and 9. Preserved the exact custom PyMOL view and subsequent image
    rotation for 6, and the source Mol* cameras and rotations for PDBe views.
11. Updated `digit-pilot/reviewed-shortlist.json` and the manifest for all
    digits 0–9. Verified source and preview hashes, clockwise camera
    transformations, and preservation of existing letters and approvals.
    Ran the search tests and existing rendering/builder tests.

## Final user-approved selections

All angles below are clockwise image rotations. All models are model 1 and
selections use the assembly's protein polymers.

| Digit | PDB | Assembly | View | Rotation |
| --- | --- | --- | --- | --- |
| 0 | 9QG9 | 1 | side | 0° |
| 1 | 9UVT | 1 | front | 70° |
| 2 | 9OJ4 | 1 | front | 90° |
| 3 | 9GC7 | 2 | front | 270° |
| 4 | 9LWI | 1 | front | 80° |
| 5 | 8OR3 | 1 | front | 90° |
| 6 | 5J4A | 1 | custom saved PyMOL view, x0/y270 | 340° |
| 7 | 9GCK | 1 | side | 20° |
| 8 | 8G2Z | 1 | side | 0° |
| 9 | 5J4A | 1 | side | 340° |

The definitions record review approval, assemblies, cameras, and provenance.
Numeric rendering still requires static tiles, layout geometry, and matching
assembly reconstruction in the application; this discovery work does not enable
numeric input.
