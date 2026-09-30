# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "pillow>=11.0",
#   "pymol-open-source==3.2.0a0",
# ]
# ///
"""Extract reproducible letter geometry metadata from the PyMOL sessions."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from PIL import Image
from pymol import cmd

# This repository script reuses the packaged builder without requiring an
# editable installation in uv's isolated script environment.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdbwords.build_letters import (  # type: ignore[import-not-found]  # noqa: E402
    ALPHABET,
    download_archive,
    prepare_sessions,
)

ASSET_DIRECTORY = Path(__file__).resolve().parent / "pdbwords/assets"


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions", type=Path, help="AlphabetPDB.zip or session directory"
    )
    parser.add_argument(
        "--images", type=Path, default=ASSET_DIRECTORY, help="letter tile directory"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ASSET_DIRECTORY / "manifest.json",
        help="manifest destination",
    )
    return parser.parse_args(arguments)


def transform_coordinate(
    coordinate: Sequence[float], rotation: Sequence[float]
) -> tuple[float, float, float]:
    x, y, z = coordinate
    return (
        rotation[0] * x + rotation[3] * y + rotation[6] * z,
        rotation[1] * x + rotation[4] * y + rotation[7] * z,
        rotation[2] * x + rotation[5] * y + rotation[8] * z,
    )


def residue_number(residue: str) -> int | None:
    match = re.match(r"-?\d+", residue)
    return int(match.group()) if match else None


def image_advance(directory: Path, letter: str) -> float:
    path = directory / f"{letter.lower()}.png"
    if path.is_file():
        with Image.open(path) as image:
            return image.width / image.height
    raise FileNotFoundError(f"No image tile found for {letter}")


def session_metadata(session: Path, image_directory: Path, letter: str) -> dict:
    cmd.reinitialize()
    cmd.load(str(session))
    objects = [
        name
        for name in cmd.get_names("objects", enabled_only=1)
        if cmd.get_type(name) == "object:molecule"
    ]
    if len(objects) != 1:
        raise ValueError(f"Expected one enabled molecule in {session}, found {objects}")

    object_name = objects[0]
    # Several official sessions hide whole chains to form a letter (notably D,
    # E, and O). Their coordinates still exist in the loaded molecule. Extract
    # the displayed cartoon rather than every protein chain in that object.
    model = cmd.get_model(f"{object_name} and polymer.protein and rep cartoon")
    view = cmd.get_view()
    rotation = list(view[:9])
    transformed = [transform_coordinate(atom.coord, rotation) for atom in model.atom]
    if not transformed:
        raise ValueError(f"No protein atoms found in {session}")

    minima = [min(point[axis] for point in transformed) for axis in range(3)]
    maxima = [max(point[axis] for point in transformed) for axis in range(3)]
    center = [(low + high) / 2 for low, high in zip(minima, maxima, strict=True)]
    size = [high - low for low, high in zip(minima, maxima, strict=True)]

    ranges: dict[str, list[int]] = {}
    for atom in model.atom:
        if atom.name != "CA":
            continue
        number = residue_number(atom.resi)
        if number is not None:
            ranges.setdefault(atom.chain, []).append(number)

    return {
        "pdb_id": object_name.upper(),
        "chains": {
            chain: [min(numbers), max(numbers)]
            for chain, numbers in sorted(ranges.items())
        },
        "rotation": [round(value, 8) for value in rotation],
        "projected_center": [round(value, 6) for value in center],
        "projected_size": [round(value, 6) for value in size],
        "advance": round(image_advance(image_directory, letter), 6),
    }


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    archive = args.sessions or download_archive(Path("build/AlphabetPDB.zip"))
    with tempfile.TemporaryDirectory(prefix="pdbwords-sessions-") as temporary:
        sessions = prepare_sessions(Path(archive), Path(temporary), ALPHABET)
        letters = {
            letter: session_metadata(sessions / f"{letter}.pse", args.images, letter)
            for letter in ALPHABET
        }

    manifest = {
        "version": 1,
        "source": "https://www.howarthgroup.org/alphabet",
        "description": "Geometry extracted from the official PyMOL sessions.",
        "cap_height": 10.0,
        "line_height": 12.0,
        "space_advance": 6.76,
        "letters": letters,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
