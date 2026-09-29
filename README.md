# pdbwords

`pdbwords` writes text using the protein alphabet curated by Mark Howarth. The
letters are protein structures from the Protein Data Bank, rendered to resemble
the Latin alphabet.

The original program was written by Kresten Lindorff-Larsen at the University
of Copenhagen in 2015. This version uses modern Python packaging and Pillow, so
ImageMagick is no longer required.

## Usage

[Install uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```console
uv run pdbwords Just write your text here
```

The result is written to `proteinword.jpg`. Choose another output path or line
length with:

```console
uv run pdbwords --output message.png --max-chars 20 Hello protein world!
```

Use the case-sensitive token `xLBx` to force a line break:

```console
uv run pdbwords First line xLBx Second line
```

Letters A-Z and the punctuation `. , ! ? : -` have dedicated images. Input is
case-insensitive. Unsupported characters are replaced with a space and reported
on standard error. Words longer than the configured line length remain intact.

Generated PNG files contain `Description`, `Software`, and `PDB IDs` text
metadata. JPEG files store the same provenance in their EXIF description and
software fields. The PDB mapping follows the A-Z table on the Howarth alphabet
page and lists each letter used in the image.

## Development

Install all dependencies and run the test suite:

```console
uv sync
uv run pytest
```

Build the source distribution and wheel, then publish them to PyPI:

```console
uv build
uv publish
```

The alphabet JPEGs are included in both distributions and installed with the
command, so a published wheel does not depend on files from this repository.

### Rebuilding the letters

The legacy JPEG tiles are only 250 pixels high. The Howarth Lab also publishes
the original A-Z PyMOL sessions, which preserve the molecular assemblies,
representations, colors, and camera views. Rebuild them as 1000-pixel-high,
transparent, lossless PNGs with:

```console
uv run --python 3.11 scripts/build_letters.py
```

The script downloads the official session archive, verifies its SHA-256 digest,
ray-traces every letter in headless PyMOL, trims transparent margins, and writes
`letters/a.png` through `letters/z.png` plus a transparent space tile. Use
`--sessions AlphabetPDB.zip` to supply an existing archive, or inspect all
options with `--help`. PyMOL is isolated as a script dependency and is not
installed with `pdbwords` or required at runtime.

PNG is used as the master format because it is lossless and supports alpha
transparency. Lossless WebP can be smaller, but would add a conversion step and
has less universal tooling support; JPEG cannot preserve transparency and adds
artifacts around fine cartoon edges. When present, PNG tiles take precedence
over the bundled legacy JPEGs. PNG word output preserves transparency, while
JPEG word output is flattened onto white.

The PyMOL sessions could also form a 3D word scene, but this is not equivalent
to concatenating coordinate files. Each structure must be transformed from its
saved camera frame, normalized to a common visual scale, and translated in the
camera plane. A combined PyMOL session or glTF scene would retain the molecular
cartoons and colors, although glTF export requires an additional geometry
conversion tool. PDB or mmCIF output would retain transformed atoms but not the
cartoon representation or material information.

## Background and license

Mark Howarth describes the alphabet, its protein structures, and the original
publication at <https://www.howarthgroup.org/alphabet>. The site permits the
alphabet files to be used freely for non-commercial purposes.

The Python code is distributed under the GNU General Public License v3.0 or
later; see [`LICENSE`](LICENSE). The bundled alphabet images retain Mark
Howarth's copyright and non-commercial-use terms; see
[`ASSET_LICENSE.md`](ASSET_LICENSE.md).

The use of AI assistance in modernizing this project is documented in
[`aidecl.yml`](aidecl.yml), following the [AI Declaration](https://ai-declaration.org/)
schema.
