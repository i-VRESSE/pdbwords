import json
import string
import zipfile
from pathlib import Path

import pytest
from molviewspec import validate_state_tree
from PIL import Image

import pdbwords


def test_words_wrap_at_maximum_line_length() -> None:
    assert pdbwords.words_to_lines(["alpha", "beta", "gamma"], max_chars=10) == [
        ["alpha", "beta"],
        ["gamma"],
    ]


def test_explicit_line_break_can_create_a_blank_line() -> None:
    assert pdbwords.words_to_lines(["one", "xLBx", "xLBx", "two"]) == [
        ["one"],
        [],
        ["two"],
    ]


def test_unknown_character_uses_space(capsys) -> None:
    directory = pdbwords.alphabet_directory()

    assert pdbwords.letter_path("@", directory) == directory / "_.png"
    assert "Unknown character '@'" in capsys.readouterr().err


def test_digits_are_rejected_by_rendering_apis(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"Digits are not supported: '2', '4'"):
        pdbwords.make_image(["42"], tmp_path / "digits.png")

    with pytest.raises(ValueError, match=r"Digits are not supported: '2', '4'"):
        pdbwords.molviewspec_state(["42"])


def test_make_image_composes_tiles_without_temporary_files(tmp_path: Path) -> None:
    output = tmp_path / "protein.png"

    pdbwords.make_image(["ab", "xLBx", "c"], output)

    with Image.open(output) as image:
        assert image.mode == "RGBA"
        assert image.size == (450, 500)
        assert image.info["Software"].startswith("pdbwords 0.2.0; Pillow")
        assert image.info["PDB IDs"] == "A=3IFZ, B=2QYC, C=2BNH"
    assert list(tmp_path.iterdir()) == [output]


def test_jpeg_contains_creation_and_pdb_metadata(tmp_path: Path) -> None:
    output = tmp_path / "protein.jpg"

    pdbwords.make_image(["Zoo!"], output)

    with Image.open(output) as image:
        exif = image.getexif()
        assert exif[305].startswith("pdbwords 0.2.0; Pillow")
        assert "Alphabet source: https://www.howarthgroup.org/alphabet" in exif[270]
        assert "PDB IDs: Z=4BTA, O=2WCD" in exif[270]


def test_render_preserves_transparent_png_tiles(tmp_path: Path) -> None:
    Image.new("RGBA", (20, 30), (255, 0, 0, 128)).save(tmp_path / "a.png")
    Image.new("RGBA", (10, 30), (255, 255, 255, 0)).save(tmp_path / "_.png")

    with pdbwords.render_lines([["a", "a"]], tmp_path) as image:
        assert image.mode == "RGBA"
        assert image.size == (50, 30)
        assert image.getchannel("A").getextrema() == (0, 128)


def test_make_image_scales_letter_height(tmp_path: Path) -> None:
    output = tmp_path / "small.png"

    pdbwords.make_image(["ab"], output, height=100)

    with Image.open(output) as image:
        assert image.size == (180, 100)


def test_all_themes_include_complete_high_resolution_alphabets() -> None:
    expected = {"_.png", *(f"{letter}.png" for letter in string.ascii_lowercase)}

    for theme in pdbwords.THEMES:
        directory = pdbwords.alphabet_directory(theme)
        assert expected <= {path.name for path in directory.glob("*.png")}
        for name in expected:
            with Image.open(directory / name) as image:
                assert image.format == "PNG"
                assert image.height == 1000


def test_themes_share_classic_punctuation_assets() -> None:
    assets = pdbwords.alphabet_directory()

    for theme in pdbwords.THEMES[1:]:
        assert pdbwords.letter_path(":", pdbwords.alphabet_directory(theme)) == (
            assets / "colon.png"
        )


def test_molviewspec_reuses_repeated_letter_structures() -> None:
    state, urls = pdbwords.molviewspec_state(["ABA"])
    downloads = [
        child for child in state["root"]["children"] if child["kind"] == "download"
    ]

    assert urls == {
        "3IFZ": "https://models.rcsb.org/3IFZ.bcif",
        "2QYC": "https://models.rcsb.org/2QYC.bcif",
    }
    assert len(downloads) == 2
    a_structure = downloads[0]["children"][0]["children"][0]
    instances = [
        child for child in a_structure["children"] if child["kind"] == "instance"
    ]
    assert len(instances) == 2
    assert all(len(instance["params"]["matrix"]) == 16 for instance in instances)
    validate_state_tree(json.dumps(state))


def test_cli_reports_unsupported_digits(tmp_path: Path, capsys) -> None:
    output = tmp_path / "42.png"
    result = pdbwords.main(["image", "-o", str(output), "42"])

    assert result == 1
    assert capsys.readouterr().err == "pdbwords: Digits are not supported: '2', '4'\n"
    assert not output.exists()


def test_themes_are_validated_and_exposed_by_cli() -> None:
    args = pdbwords.parse_args(["image", "--theme", "tube", "Hello"])

    assert args.theme == "tube"
    assert pdbwords.validate_theme("oval") == "oval"

    try:
        pdbwords.validate_theme("unknown")
    except ValueError as error:
        assert "choose from classic, loop, oval, tube" in str(error)
    else:
        raise AssertionError("invalid theme was accepted")


def test_make_online_mvsx(tmp_path: Path) -> None:
    output = tmp_path / "word.mvsx"

    pdbwords.make_molviewspec(["A"], output)

    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["index.mvsj"]
        state = json.loads(archive.read("index.mvsj"))
    assert state["metadata"]["title"] == "pdbwords: A"


def test_cli_uses_distinct_image_and_mvs_subcommands() -> None:
    image_args = pdbwords.parse_args(["image", "--height", "500", "Hello"])
    mvs_args = pdbwords.parse_args(["mvs", "--offline", "Hello"])

    assert (image_args.command, image_args.output, image_args.height) == (
        "image",
        Path("proteinword.jpg"),
        500,
    )
    assert (mvs_args.command, mvs_args.output, mvs_args.offline) == (
        "mvs",
        None,
        True,
    )
