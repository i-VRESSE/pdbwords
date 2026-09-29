from pathlib import Path

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

    assert pdbwords.letter_path("@", directory) == directory / "_.jpg"
    assert "Unknown character '@'" in capsys.readouterr().err


def test_make_image_composes_tiles_without_temporary_files(tmp_path: Path) -> None:
    output = tmp_path / "protein.png"

    pdbwords.make_image(["ab", "xLBx", "c"], output)

    with Image.open(output) as image:
        assert image.mode == "RGB"
        assert image.size == (443, 500)
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
