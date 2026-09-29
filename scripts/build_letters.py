# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "pillow>=11.0",
#   "pymol-open-source==3.2.0a0",
# ]
# ///
"""Render high-resolution protein letters from the official PyMOL sessions."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path

from PIL import Image
from pymol import cmd

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ARCHIVE_URL = "https://www.howarthgroup.org/alphabet_htm_files/AlphabetPDB.zip"
ARCHIVE_SHA256 = "7c29b73b60cbf687072c41e256cda0bc0228563c23ffb3b130165ca75f799231"


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions",
        type=Path,
        help="official AlphabetPDB.zip or a directory containing A.pse through Z.pse",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("letters"),
        help="PNG destination (default: letters)",
    )
    parser.add_argument(
        "--letters",
        default=ALPHABET,
        help="letters to render (default: A-Z)",
    )
    parser.add_argument(
        "--render-size",
        type=int,
        default=2000,
        metavar="PX",
        help="square PyMOL ray-tracing size (default: 2000)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1000,
        metavar="PX",
        help="normalized output tile height (default: 1000)",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.02,
        metavar="FRACTION",
        help="transparent padding relative to render size (default: 0.02)",
    )
    return parser.parse_args(arguments)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_archive(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        print(f"Downloading {ARCHIVE_URL}")
        with (
            urllib.request.urlopen(ARCHIVE_URL) as response,
            destination.open("wb") as output,
        ):
            shutil.copyfileobj(response, output)

    actual_hash = sha256(destination)
    if actual_hash != ARCHIVE_SHA256:
        raise ValueError(
            f"Unexpected SHA-256 for {destination}: {actual_hash}; "
            f"expected {ARCHIVE_SHA256}"
        )
    return destination


def prepare_sessions(source: Path, destination: Path, letters: str) -> Path:
    if source.is_dir():
        nested = source / "AlphabetPDB"
        return nested if nested.is_dir() else source

    with zipfile.ZipFile(source) as archive:
        for letter in letters:
            member = f"AlphabetPDB/{letter}.pse"
            with (
                archive.open(member) as input_stream,
                (destination / f"{letter}.pse").open("wb") as output_stream,
            ):
                shutil.copyfileobj(input_stream, output_stream)
    return destination


def trim_and_resize(source: Path, destination: Path, height: int, padding: int) -> None:
    with Image.open(source) as opened:
        image = opened.convert("RGBA")

    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"PyMOL rendered an empty image for {source.stem}")

    left, top, right, bottom = bounds
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    cropped = image.crop((left, top, right, bottom))
    width = max(1, round(cropped.width * height / cropped.height))
    resized = cropped.resize((width, height), Image.Resampling.LANCZOS)
    resized.save(destination, optimize=True, compress_level=9, dpi=(300, 300))
    resized.close()
    cropped.close()
    image.close()


def render_letters(
    sessions: Path,
    output_directory: Path,
    letters: str,
    render_size: int,
    height: int,
    padding_fraction: float,
) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    padding = round(render_size * padding_fraction)

    with tempfile.TemporaryDirectory(prefix="pdbwords-render-") as temporary:
        temporary_directory = Path(temporary)
        for letter in letters:
            session = sessions / f"{letter}.pse"
            if not session.is_file():
                raise FileNotFoundError(f"Missing PyMOL session: {session}")

            raw_output = temporary_directory / f"{letter}.png"
            final_output = output_directory / f"{letter.lower()}.png"
            print(f"Rendering {letter} -> {final_output}")
            cmd.reinitialize()
            cmd.load(str(session))
            cmd.set("ray_opaque_background", 0)
            cmd.set("antialias", 2)
            cmd.ray(render_size, render_size)
            cmd.png(str(raw_output), quiet=1)
            trim_and_resize(raw_output, final_output, height, padding)

    space_width = round(height * 169 / 250)
    Image.new("RGBA", (space_width, height), (255, 255, 255, 0)).save(
        output_directory / "_.png", optimize=True, compress_level=9, dpi=(300, 300)
    )


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    letters = "".join(dict.fromkeys(args.letters.upper()))
    if not letters or any(letter not in ALPHABET for letter in letters):
        raise ValueError("--letters must contain only A-Z")
    if args.render_size < 1 or args.height < 1:
        raise ValueError("--render-size and --height must be positive")
    if not 0 <= args.padding < 0.5:
        raise ValueError("--padding must be between 0 and 0.5")

    archive = args.sessions or download_archive(Path("build/AlphabetPDB.zip"))
    with tempfile.TemporaryDirectory(prefix="pdbwords-sessions-") as temporary:
        sessions = prepare_sessions(Path(archive), Path(temporary), letters)
        render_letters(
            sessions,
            args.output_dir,
            letters,
            args.render_size,
            args.height,
            args.padding,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
