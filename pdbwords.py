"""Write text using Mark Howarth's protein alphabet."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from importlib.resources import files
from pathlib import Path

from PIL import Image, PngImagePlugin
from PIL import __version__ as pillow_version

VERSION = "0.2.0"
DEFAULT_OUTPUT = Path("proteinword.jpg")
DEFAULT_MAX_CHARS = 25
LINE_BREAK = "xLBx"
ALPHABET_URL = "https://www.howarthgroup.org/alphabet"
SPECIAL_CHARACTERS = {
    " ": "_",
    ".": "stop",
    "!": "exclamation",
    "?": "question",
    ",": "comma",
    ":": "colon",
    "-": "hyphen",
}
PDB_IDS = dict(
    zip(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        (
            "3IFZ",
            "2QYC",
            "2BNH",
            "4J3O",
            "2Q5R",
            "3J04",
            "4U48",
            "1XU9",
            "3H7X",
            "1B3U",
            "4OX0",
            "1UEB",
            "1OU5",
            "1Z85",
            "2WCD",
            "3AFC",
            "3SZV",
            "2ARP",
            "2OT8",
            "3E98",
            "2VWE",
            "3H90",
            "4CJ9",
            "1W3B",
            "1IGT",
            "4BTA",
        ),
        strict=True,
    )
)


def alphabet_directory() -> Path:
    """Find alphabet images in a checkout or an installed environment."""
    source_directory = Path(__file__).resolve().with_name("letters")
    if source_directory.is_dir():
        return source_directory

    try:
        installed_directory = files("pdbwords_assets")
    except ModuleNotFoundError:
        pass
    else:
        if installed_directory.is_dir():
            return Path(str(installed_directory))

    raise FileNotFoundError("Could not find the pdbwords alphabet images")


def letter_path(character: str, directory: Path) -> Path:
    """Return an image for a character, falling back to a blank tile."""
    name = SPECIAL_CHARACTERS.get(character, character.lower())
    for suffix in (".png", ".jpg"):
        path = directory / f"{name}{suffix}"
        if path.is_file():
            return path

    print(
        f"Unknown character {character!r}; replacing it with a space.",
        file=sys.stderr,
    )
    for suffix in (".png", ".jpg"):
        path = directory / f"_{suffix}"
        if path.is_file():
            return path
    raise FileNotFoundError("Could not find the pdbwords space image")


def words_to_lines(
    words: Sequence[str],
    max_chars: int = DEFAULT_MAX_CHARS,
    line_break: str = LINE_BREAK,
) -> list[list[str]]:
    """Wrap words without splitting them, honoring explicit line breaks."""
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")

    lines: list[list[str]] = []
    line: list[str] = []
    line_length = 0

    for word in words:
        if word == line_break:
            lines.append(line)
            line = []
            line_length = 0
            continue

        added_length = len(word) + (1 if line else 0)
        if line and line_length + added_length > max_chars:
            lines.append(line)
            line = [word]
            line_length = len(word)
        else:
            line.append(word)
            line_length += added_length

    if line or not lines:
        lines.append(line)

    return lines


def _join_images(images: Sequence[Image.Image], *, horizontal: bool) -> Image.Image:
    if horizontal:
        size = (
            sum(image.width for image in images),
            max(image.height for image in images),
        )
    else:
        size = (
            max(image.width for image in images),
            sum(image.height for image in images),
        )

    mode = "RGBA" if any(image.mode == "RGBA" for image in images) else "RGB"
    background = (255, 255, 255, 0) if mode == "RGBA" else "white"
    result = Image.new(mode, size, background)
    offset = 0
    for image in images:
        position = (offset, 0) if horizontal else (0, offset)
        result.paste(image, position)
        offset += image.width if horizontal else image.height
    return result


def render_lines(
    lines: Sequence[Sequence[str]], directory: Path | None = None
) -> Image.Image:
    """Render wrapped lines into one RGB image."""
    directory = directory or alphabet_directory()
    blank_path = letter_path(" ", directory)
    rendered_lines: list[Image.Image] = []

    with ExitStack() as stack:
        for line in lines:
            paths: list[Path] = []
            for index, word in enumerate(line):
                if index:
                    paths.append(blank_path)
                paths.extend(letter_path(character, directory) for character in word)

            if not paths:
                paths.append(blank_path)

            tiles: list[Image.Image] = []
            for path in paths:
                source = stack.enter_context(Image.open(path))
                mode = (
                    "RGBA"
                    if source.mode == "RGBA" or "transparency" in source.info
                    else "RGB"
                )
                tile = source.convert(mode)
                stack.callback(tile.close)
                tiles.append(tile)
            rendered_lines.append(_join_images(tiles, horizontal=True))

        return _join_images(rendered_lines, horizontal=False)


def image_metadata(words: Sequence[str]) -> dict[str, str]:
    """Describe how an image was made and the structures represented in it."""
    used_ids: dict[str, str] = {}
    for word in words:
        if word == LINE_BREAK:
            continue
        for character in word.upper():
            if character in PDB_IDS:
                used_ids.setdefault(character, PDB_IDS[character])

    return {
        "Description": (
            "Created with pdbwords using Mark Howarth's protein alphabet. "
            f"Alphabet source: {ALPHABET_URL}"
        ),
        "Software": f"pdbwords {VERSION}; Pillow {pillow_version}",
        "PDB IDs": ", ".join(
            f"{letter}={pdb_id}" for letter, pdb_id in used_ids.items()
        ),
    }


def save_image(image: Image.Image, output: Path, metadata: dict[str, str]) -> None:
    """Save an image with provenance in the format's native metadata."""
    if output.suffix.lower() == ".png":
        png_info = PngImagePlugin.PngInfo()
        for key, value in metadata.items():
            png_info.add_text(key, value)
        image.save(output, pnginfo=png_info)
        return

    exif = Image.Exif()
    exif[270] = f"{metadata['Description']} PDB IDs: {metadata['PDB IDs']}"
    exif[305] = metadata["Software"]
    if image.mode == "RGBA" and output.suffix.lower() in {".jpg", ".jpeg"}:
        flattened = Image.new("RGB", image.size, "white")
        flattened.paste(image, mask=image.getchannel("A"))
        flattened.save(output, exif=exif)
        flattened.close()
    else:
        image.save(output, exif=exif)


def make_image(
    words: Sequence[str],
    output: Path = DEFAULT_OUTPUT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Path:
    """Render words and save the resulting image."""
    with render_lines(words_to_lines(words, max_chars=max_chars)) as image:
        save_image(image, output, image_metadata(words))
    return output


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write text using Mark Howarth's protein alphabet."
    )
    parser.add_argument(
        "text", nargs="+", help=f"text to render; use {LINE_BREAK} for a line break"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output image (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        metavar="N",
        help=f"maximum characters per line (default: {DEFAULT_MAX_CHARS})",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        make_image(args.text, args.output, args.max_chars)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"pdbwords: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
