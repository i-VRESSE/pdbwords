"""Write text using Mark Howarth's protein alphabet."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
import zipfile
from collections.abc import Sequence
from contextlib import ExitStack
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from PIL import Image, PngImagePlugin
from PIL import __version__ as pillow_version

VERSION = "0.2.0"
DEFAULT_OUTPUT = Path("proteinword.jpg")
DEFAULT_MVS_OUTPUT = Path("proteinword.mvsj")
DEFAULT_OFFLINE_MVS_OUTPUT = Path("proteinword.mvsx")
DEFAULT_MAX_CHARS = 25
DEFAULT_LETTER_HEIGHT = 250
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


def load_manifest(directory: Path | None = None) -> dict[str, Any]:
    """Load molecular geometry shared by image and MolViewSpec generation."""
    path = (directory or alphabet_directory()) / "manifest.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


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
    lines: Sequence[Sequence[str]],
    directory: Path | None = None,
    height: int | None = None,
) -> Image.Image:
    """Render wrapped lines into one image, optionally scaling each tile."""
    if height is not None and height < 1:
        raise ValueError("height must be at least 1")

    directory = directory or alphabet_directory()
    blank_path = letter_path(" ", directory)
    rendered_lines: list[Image.Image] = []
    tiles_by_path: dict[Path, Image.Image] = {}

    with ExitStack() as stack:
        for line in lines:
            paths: list[Path] = []
            for index, word in enumerate(line):
                if index:
                    paths.append(blank_path)
                paths.extend(letter_path(character, directory) for character in word)

            if not paths:
                paths.append(blank_path)

            for path in dict.fromkeys(paths):
                if path in tiles_by_path:
                    continue
                source = stack.enter_context(Image.open(path))
                mode = (
                    "RGBA"
                    if source.mode == "RGBA" or "transparency" in source.info
                    else "RGB"
                )
                tile = source.convert(mode)
                if height is not None and tile.height != height:
                    width = max(1, round(tile.width * height / tile.height))
                    resized = tile.resize((width, height), Image.Resampling.LANCZOS)
                    tile.close()
                    tile = resized
                stack.callback(tile.close)
                tiles_by_path[path] = tile

            rendered_lines.append(
                _join_images([tiles_by_path[path] for path in paths], horizontal=True)
            )

        result = _join_images(rendered_lines, horizontal=False)
        for line in rendered_lines:
            line.close()
        return result


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
    height: int = DEFAULT_LETTER_HEIGHT,
) -> Path:
    """Render words and save the resulting image."""
    with render_lines(
        words_to_lines(words, max_chars=max_chars), height=height
    ) as image:
        save_image(image, output, image_metadata(words))
    return output


RAINBOW = (
    "#0000FF",
    "#0066FF",
    "#00CCFF",
    "#00DD88",
    "#33CC33",
    "#AADD00",
    "#FFFF00",
    "#FFBB00",
    "#FF7700",
    "#FF2200",
)


def _mvs_matrix(letter: dict[str, Any], position: tuple[float, float]) -> list[float]:
    rotation = letter["rotation"]
    center = letter["projected_center"]
    translation = [
        position[0] - center[0],
        position[1] - center[1],
        -center[2],
    ]
    return [
        rotation[0],
        rotation[1],
        rotation[2],
        0,
        rotation[3],
        rotation[4],
        rotation[5],
        0,
        rotation[6],
        rotation[7],
        rotation[8],
        0,
        *translation,
        1,
    ]


def _mvs_positions(
    lines: Sequence[Sequence[str]], manifest: dict[str, Any]
) -> tuple[dict[str, list[tuple[float, float]]], float, float]:
    cap_height = manifest["cap_height"]
    line_height_ratio = manifest["line_height"] / cap_height
    space_advance_ratio = manifest["space_advance"] / cap_height
    letters = manifest["letters"]
    positions: dict[str, list[tuple[float, float]]] = {}
    widths: list[float] = []

    rendered_lines = [" ".join(line).upper() for line in lines]
    letter_heights = [
        letters[character]["projected_size"][1]
        for line in rendered_lines
        for character in line
        if character in letters
    ]
    native_cap_height = max(letter_heights, default=cap_height)
    line_height = native_cap_height * line_height_ratio
    for line_index, line in enumerate(rendered_lines):
        advances = [
            letters[character]["advance"] * letters[character]["projected_size"][1]
            if character in letters
            else space_advance_ratio * native_cap_height
            for character in line
        ]
        width = sum(advances)
        widths.append(width)
        cursor = -width / 2
        y = ((len(rendered_lines) - 1) / 2 - line_index) * line_height
        for character, advance in zip(line, advances, strict=True):
            if character in letters:
                positions.setdefault(character, []).append((cursor + advance / 2, y))
            cursor += advance

    return positions, max(widths, default=native_cap_height), len(lines) * line_height


def _color_nodes(chains: dict[str, list[int]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for chain, (first, last) in chains.items():
        count = last - first + 1
        for index, color in enumerate(RAINBOW):
            begin = first + count * index // len(RAINBOW)
            end = first + count * (index + 1) // len(RAINBOW) - 1
            if begin <= end:
                nodes.append(
                    {
                        "kind": "color",
                        "params": {
                            "color": color,
                            "selector": {
                                "auth_asym_id": chain,
                                "beg_auth_seq_id": begin,
                                "end_auth_seq_id": end,
                            },
                        },
                    }
                )
    return nodes


def molviewspec_state(
    words: Sequence[str],
    max_chars: int = DEFAULT_MAX_CHARS,
    *,
    local_structures: bool = False,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Create a MolViewSpec state and its PDB-ID-to-URL mapping."""
    manifest = load_manifest()
    lines = words_to_lines(words, max_chars=max_chars)
    positions, width, height = _mvs_positions(lines, manifest)
    children: list[dict[str, Any]] = []
    urls: dict[str, str] = {}

    for character, letter_positions in positions.items():
        letter = manifest["letters"][character]
        pdb_id = letter["pdb_id"]
        url = (
            f"structures/{pdb_id}.bcif"
            if local_structures
            else f"https://models.rcsb.org/{pdb_id}.bcif"
        )
        urls[pdb_id] = url
        instances = [
            {
                "kind": "instance",
                "params": {"matrix": _mvs_matrix(letter, position)},
            }
            for position in letter_positions
        ]
        selector = [{"auth_asym_id": chain} for chain in letter["chains"]]
        component = {
            "kind": "component",
            "params": {"selector": selector},
            "children": [
                {
                    "kind": "representation",
                    "params": {"type": "cartoon"},
                    "children": _color_nodes(letter["chains"]),
                },
                {
                    "kind": "tooltip",
                    "params": {"text": f"{character}: PDB {pdb_id}"},
                },
            ],
        }
        structure = {
            "kind": "structure",
            "params": {"type": "model"},
            "children": [*instances, component],
        }
        children.append(
            {
                "kind": "download",
                "params": {"url": url},
                "children": [
                    {
                        "kind": "parse",
                        "params": {"format": "bcif"},
                        "children": [structure],
                    }
                ],
            }
        )

    camera_distance = max(width, height, manifest["cap_height"]) * 1.25
    children.extend(
        [
            {"kind": "canvas", "params": {"background_color": "white"}},
            {
                "kind": "camera",
                "params": {
                    "target": [0, 0, 0],
                    "position": [0, 0, camera_distance],
                    "up": [0, 1, 0],
                },
            },
        ]
    )
    state = {
        "kind": "single",
        "root": {"kind": "root", "children": children},
        "metadata": {
            "title": f"pdbwords: {' '.join(words)}",
            "description": (
                "Created with pdbwords from Mark Howarth's protein alphabet."
            ),
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "1.8",
        },
    }
    return state, urls


def make_molviewspec(
    words: Sequence[str],
    output: Path,
    max_chars: int = DEFAULT_MAX_CHARS,
    *,
    offline: bool = False,
) -> Path:
    """Write an online MVSJ or optionally self-contained MVSX scene."""
    suffix = output.suffix.lower()
    if suffix not in {".mvsj", ".mvsx"}:
        raise ValueError("MolViewSpec output must end in .mvsj or .mvsx")
    if offline and suffix != ".mvsx":
        raise ValueError("--offline requires .mvsx output")

    state, urls = molviewspec_state(
        words, max_chars=max_chars, local_structures=offline
    )
    serialized = json.dumps(state, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".mvsj":
        output.write_text(serialized, encoding="utf-8")
        return output

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.mvsj", serialized)
        if offline:
            for pdb_id in urls:
                source_url = f"https://models.rcsb.org/{pdb_id}.bcif"
                print(f"Downloading {source_url}")
                with (
                    urllib.request.urlopen(source_url, timeout=60) as response,
                    archive.open(f"structures/{pdb_id}.bcif", "w") as destination,
                ):
                    shutil.copyfileobj(response, destination)
    return output


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write text using Mark Howarth's protein alphabet."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    image_parser = commands.add_parser("image", help="render a static image")
    image_parser.add_argument(
        "text", nargs="+", help=f"text to render; use {LINE_BREAK} for a line break"
    )
    image_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output image (default: {DEFAULT_OUTPUT})",
    )
    image_parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        metavar="N",
        help=f"maximum characters per line (default: {DEFAULT_MAX_CHARS})",
    )
    image_parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_LETTER_HEIGHT,
        metavar="PX",
        help=f"image letter height (default: {DEFAULT_LETTER_HEIGHT})",
    )

    mvs_parser = commands.add_parser("mvs", help="render an interactive 3D word")
    mvs_parser.add_argument(
        "text", nargs="+", help=f"text to render; use {LINE_BREAK} for a line break"
    )
    mvs_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            f".mvsj or .mvsx output (default: {DEFAULT_MVS_OUTPUT}, "
            f"or {DEFAULT_OFFLINE_MVS_OUTPUT} with --offline)"
        ),
    )
    mvs_parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        metavar="N",
        help=f"maximum characters per line (default: {DEFAULT_MAX_CHARS})",
    )
    mvs_parser.add_argument(
        "--offline",
        action="store_true",
        help="bundle RCSB coordinates in .mvsx output",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        if args.command == "mvs":
            output = args.output or (
                DEFAULT_OFFLINE_MVS_OUTPUT if args.offline else DEFAULT_MVS_OUTPUT
            )
            make_molviewspec(args.text, output, args.max_chars, offline=args.offline)
        else:
            make_image(args.text, args.output, args.max_chars, args.height)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"pdbwords: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
